package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestParseThreeProviderRecords(t *testing.T) {
	cases := []struct{ source, payload, year, doi string }{
		{"crossref", `{"message":{"items":[{"DOI":"10.1/test","title":["Test title"],"published":{"date-parts":[[2020,2,3]]}}]}}`, "2020", "10.1/test"},
		{"openalex", `{"results":[{"doi":"https://doi.org/10.1/x","display_name":"Test title","publication_year":2023}]}`, "2023", "https://doi.org/10.1/x"},
		{"europepmc", `{"resultList":{"result":[{"doi":"10.1/abc","title":"Test title","pubYear":"2022"}]}}`, "2022", "10.1/abc"},
	}
	for _, c := range cases {
		records, err := parsePapers(c.source, []byte(c.payload), 2)
		if err != nil || len(records) != 1 || records[0].Source != c.source || records[0].DOI != c.doi || records[0].Year != c.year {
			t.Fatalf("bad %v %v %v", c.source, records, err)
		}
	}
}
func TestParserBoundsAndUnsupportedSource(t *testing.T) {
	data := `{"message":{"items":[{"title":[],"DOI":""},{"title":["` + strings.Repeat("X", 800) + `"],"DOI":"` + strings.Repeat("d", 350) + `"}]}}`
	out, err := parsePapers("crossref", []byte(data), 5)
	if err != nil || len(out) != 1 || len(out[0].Title) != 700 || out[0].DOI != "" {
		t.Fatalf("%v %v", out, err)
	}
	if _, err := parsePapers("bogus", []byte("{}"), 1); err == nil {
		t.Fatal("unsupported source accepted")
	}
	if _, err := parsePapers("crossref", []byte("invalid"), 1); err == nil {
		t.Fatal("bad JSON accepted")
	}
	data = `{"resultList":{"result":[{"doi":"10.1/x","title":"Title","pubYear":"` + strings.Repeat("2", 12) + `"}]}}`
	out, _ = parsePapers("europepmc", []byte(data), 2)
	if out[0].Year != "" {
		t.Fatal("invalid year retained")
	}
	for _, tc := range []struct{ source, payload string }{
		{"crossref", `{"message":{"items":[{"DOI":"10.1/x","title":["Name"]},{"DOI":"10.1/y","title":["Other"]}]}}`},
		{"openalex", `{"results":[{"doi":"10.1/x","display_name":"Name"},{"doi":"10.1/y","display_name":"Other"}]}`},
		{"europepmc", `{"resultList":{"result":[{"doi":"10.1/x","title":"Name"},{"doi":"10.1/y","title":"Other"}]}}`},
	} {
		out, err = parsePapers(tc.source, []byte(tc.payload), 1)
		if err != nil || len(out) != 1 {
			t.Fatalf("bad limit %s %v %v", tc.source, out, err)
		}
	}
}
func TestEndToEndRecordModeAndFailures(t *testing.T) {
	answer := map[string]string{
		"/works":  `{"results":[{"doi":"10.1/abc","display_name":"Study"}]}`,
		"/search": `{"resultList":{"result":[{"title":"Result","doi":"10.1/abc"}]}}`,
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "/works") {
			if r.URL.Query().Get("search") != "" {
				_, _ = w.Write([]byte(answer["/works"]))
			} else {
				_, _ = w.Write([]byte(`{"message":{"items":[{"DOI":"10.1/x","title":["Name"]}]}}`))
			}
		} else {
			_, _ = w.Write([]byte(answer["/search"]))
		}
	}))
	defer srv.Close()
	fake := []struct{ name, endpoint string }{{"crossref", srv.URL + "/works"}, {"openalex", srv.URL + "/works"}, {"europepmc", srv.URL + "/search"}}
	r := execute(context.Background(), srv.Client(), Request{Query: "biology", Limit: 1, Mode: "records"}, fake)
	if r.Status != "PROVIDER_RECORDS_ONLY_UNVERIFIED" {
		t.Fatalf("%v", r)
	}
	for _, part := range r.Results {
		if len(part.Records) != 1 || part.Records[0].DOI == "" {
			t.Fatalf("%+v", part)
		}
	}
	if validate(Request{Query: "trial", Limit: 2, Mode: "invalid"}) == nil {
		t.Fatal("invalid mode accepted")
	}
}
func TestSchemaErrorStopsUntrustedRecords(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"message":{"items":"invalid"}}`))
	}))
	defer srv.Close()
	r := single(context.Background(), srv.Client(), "crossref", srv.URL, Request{Query: "research", Limit: 1, Mode: "records"})
	if r.Error != "provider response schema invalid" {
		t.Fatalf("%+v", r)
	}
}
func TestRecordsResultNeverClaimsEvidence(t *testing.T) {
	b, _ := json.Marshal(Response{Status: "PROVIDER_RECORDS_ONLY_UNVERIFIED", Results: []Status{{Source: "crossref"}}})
	if strings.Contains(string(b), "scientific_validity_assessed") {
		t.Fatal("fabricated judgment")
	}
}
