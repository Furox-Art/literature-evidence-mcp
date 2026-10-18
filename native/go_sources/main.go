// A bounded three-provider HTTP query worker for Literature Evidence MCP.
// One JSON request on stdin, one JSON result on stdout. Never sends to
// user-supplied URLs: provider endpoints are compiled-in and fixed.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"
)

type Request struct {
	Query string `json:"query"`
	Limit int    `json:"limit"`
	Mode  string `json:"mode,omitempty"`
}
type Paper struct {
	Source string `json:"source"`
	DOI    string `json:"doi,omitempty"`
	Title  string `json:"title,omitempty"`
	Year   string `json:"year,omitempty"`
}
type Status struct {
	Records    []Paper `json:"records,omitempty"`
	Source     string  `json:"source"`
	HTTPStatus int     `json:"http_status"`
	Bytes      int     `json:"bytes"`
	Error      string  `json:"error,omitempty"`
}
type Response struct {
	Status  string   `json:"status"`
	Results []Status `json:"results"`
	Notice  string   `json:"notice"`
}

var bases = []struct{ name, endpoint string }{
	{"crossref", "https://api.crossref.org/works"},
	{"openalex", "https://api.openalex.org/works"},
	{"europepmc", "https://www.ebi.ac.uk/europepmc/webservices/rest/search"},
}

func queryPath(base, name string, request Request) (string, error) {
	u, err := url.Parse(base)
	if err != nil {
		return "", err
	}
	q := u.Query()
	switch name {
	case "crossref":
		q.Set("query", request.Query)
		q.Set("rows", fmt.Sprint(request.Limit))
	case "openalex":
		q.Set("search", request.Query)
		q.Set("per_page", fmt.Sprint(request.Limit))
	case "europepmc":
		q.Set("query", request.Query)
		q.Set("pageSize", fmt.Sprint(request.Limit))
		q.Set("format", "json")
	default:
		return "", errors.New("unknown source")
	}
	u.RawQuery = q.Encode()
	return u.String(), nil
}

func single(ctx context.Context, client *http.Client, source, endpoint string, request Request) Status {
	result := Status{Source: source}
	target, err := queryPath(endpoint, source, request)
	if err != nil {
		result.Error = "invalid provider configuration"
		return result
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, target, nil)
	if err != nil {
		result.Error = "request setup failed"
		return result
	}
	req.Header.Set("Accept", "application/json")
	resp, err := client.Do(req)
	if err != nil {
		result.Error = "provider unavailable"
		return result
	}
	defer resp.Body.Close()
	result.HTTPStatus = resp.StatusCode
	reader := io.LimitReader(resp.Body, 2*1024*1024+1)
	payload, err := io.ReadAll(reader)
	if err != nil {
		result.Error = "provider body read failed"
		return result
	}
	if len(payload) > 2*1024*1024 {
		result.Error = "provider body exceeded 2MiB"
		return result
	}
	result.Bytes = len(payload)
	if resp.StatusCode != http.StatusOK {
		result.Error = "provider returned non-200"
		return result
	}
	if !json.Valid(payload) {
		result.Error = "provider body is not JSON"
		return result
	}
	if request.Mode == "records" {
		records, parseErr := parsePapers(source, payload, request.Limit)
		if parseErr != nil {
			result.Error = "provider response schema invalid"
			return result
		}
		result.Records = records
	}
	return result
}

// Parse only limited provider metadata. Never trust provider text as
// scientific evidence; no PDF retrieval or arbitrary URL following.
func parsePapers(source string, payload []byte, limit int) ([]Paper, error) {
	// Separate wire structs prevent provider fields from being mistaken for evidence.
	type crItem struct {
		DOI       string   `json:"DOI"`
		Title     []string `json:"title"`
		Published struct {
			DateParts [][]int `json:"date-parts"`
		} `json:"published"`
	}
	var raw struct {
		Message struct {
			Items []crItem `json:"items"`
		} `json:"message"`
		Results []struct {
			DOI             string `json:"doi"`
			DisplayName     string `json:"display_name"`
			PublicationYear int    `json:"publication_year"`
		} `json:"results"`
		ResultList struct {
			Result []struct {
				DOI     string `json:"doi"`
				Title   string `json:"title"`
				PubYear string `json:"pubYear"`
			} `json:"result"`
		} `json:"resultList"`
	}
	if err := json.Unmarshal(payload, &raw); err != nil {
		return nil, err
	}
	out := make([]Paper, 0, limit)
	add := func(doi, title, year string) {
		if len(out) >= limit {
			return
		}
		if len(title) > 700 {
			title = title[:700]
		}
		if len(doi) > 300 {
			doi = ""
		}
		if len(year) > 8 {
			year = ""
		}
		if title == "" && doi == "" {
			return
		}
		out = append(out, Paper{Source: source, DOI: doi, Title: title, Year: year})
	}
	switch source {
	case "crossref":
		for _, paper := range raw.Message.Items {
			title := ""
			if len(paper.Title) > 0 {
				title = paper.Title[0]
			}
			year := ""
			if len(paper.Published.DateParts) > 0 && len(paper.Published.DateParts[0]) > 0 {
				year = fmt.Sprint(paper.Published.DateParts[0][0])
			}
			add(paper.DOI, title, year)
		}
	case "openalex":
		for _, paper := range raw.Results {
			year := ""
			if paper.PublicationYear > 0 {
				year = fmt.Sprint(paper.PublicationYear)
			}
			add(paper.DOI, paper.DisplayName, year)
		}
	case "europepmc":
		for _, paper := range raw.ResultList.Result {
			add(paper.DOI, paper.Title, paper.PubYear)
		}
	default:
		return nil, errors.New("unknown source")
	}
	return out, nil
}

func execute(ctx context.Context, client *http.Client, request Request, providers []struct{ name, endpoint string }) Response {
	status := "PROVIDER_STATUS_ONLY"
	if request.Mode == "records" {
		status = "PROVIDER_RECORDS_ONLY_UNVERIFIED"
	}
	result := Response{Status: status, Results: make([]Status, len(providers)), Notice: "Reachability is not relevance, bibliographic accuracy or scientific validity."}
	var wg sync.WaitGroup
	for i, p := range providers {
		wg.Add(1)
		go func(i int, name, endpoint string) {
			defer wg.Done()
			result.Results[i] = single(ctx, client, name, endpoint, request)
		}(i, p.name, p.endpoint)
	}
	wg.Wait()
	return result
}

func validate(request Request) error {
	if len(strings.TrimSpace(request.Query)) < 2 || len(request.Query) > 500 {
		return errors.New("query length must be 2-500")
	}
	if request.Mode != "" && request.Mode != "status" && request.Mode != "records" {
		return errors.New("invalid probe mode")
	}
	if request.Limit < 1 || request.Limit > 20 {
		return errors.New("limit must be 1-20")
	}
	return nil
}

func run(in io.Reader, out io.Writer, client *http.Client) error {
	decoder := json.NewDecoder(io.LimitReader(in, 16*1024+1))
	decoder.DisallowUnknownFields()
	var input Request
	if err := decoder.Decode(&input); err != nil {
		return fmt.Errorf("invalid request: %w", err)
	}
	var extra json.RawMessage
	if err := decoder.Decode(&extra); err != io.EOF {
		return errors.New("expected one request")
	}
	if err := validate(input); err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	return json.NewEncoder(out).Encode(execute(ctx, client, input, bases))
}

func main() {
	os.Exit(serveMain(os.Stdin, os.Stdout, os.Stderr, &http.Client{Timeout: 12 * time.Second}))
}

func serveMain(in io.Reader, out, errOut io.Writer, client *http.Client) int {
	if err := run(in, out, client); err != nil {
		fmt.Fprintln(errOut, err)
		return 1
	}
	return 0
}
