package main

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"
)

func TestUrlAndInputLimits(t *testing.T) {
	for _, name := range []string{"crossref", "openalex", "europepmc"} {
		u, err := queryPath("https://example.org/path", name, Request{Query: "science & biology", Limit: 4})
		if err != nil {
			t.Fatal(err)
		}
		parsed, _ := url.Parse(u)
		param := parsed.Query()
		if param.Get("query") == "" && param.Get("search") == "" {
			t.Fatalf("no query for %v", name)
		}
	}
	if _, err := queryPath("bad://host", "other", Request{}); err == nil {
		t.Fatal("invalid source accepted")
	}
	if _, err := queryPath("%", "crossref", Request{}); err == nil {
		t.Fatal("invalid URL accepted")
	}
	for _, r := range []Request{{Query: "a", Limit: 1}, {Query: "valid", Limit: 0}, {Query: "valid", Limit: 21}, {Query: strings.Repeat("x", 501), Limit: 1}} {
		if validate(r) == nil {
			t.Fatalf("accepted bad request %+v", r)
		}
	}
	if validate(Request{Query: "valid", Limit: 2}) != nil {
		t.Fatal("valid request refused")
	}
}
func TestResponseBranches(t *testing.T) {
	for _, test := range []struct {
		body string
		code int
		want string
	}{
		{body: `{"ok":1}`, code: 200, want: ""},
		{body: "<broken>", code: 200, want: "not JSON"},
		{body: "error", code: 500, want: "non-200"},
		{body: strings.Repeat("x", 2*1024*1024+1), code: 200, want: "exceeded"},
	} {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Header.Get("Accept") != "application/json" {
				t.Error("bad Accept")
			}
			w.WriteHeader(test.code)
			_, _ = io.WriteString(w, test.body)
		}))
		s := single(context.Background(), srv.Client(), "crossref", srv.URL, Request{Query: "test", Limit: 2})
		if !strings.Contains(s.Error, test.want) {
			t.Fatalf("want %q got %+v", test.want, s)
		}
		srv.Close()
	}
}
func TestNetworkFailuresAndConcurrency(t *testing.T) {
	c := &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) { return nil, errors.New("offline") })}
	s := single(context.Background(), c, "crossref", "https://example.org", Request{Query: "test", Limit: 2})
	if s.Error != "provider unavailable" {
		t.Fatalf("%+v", s)
	}
	errSource := single(context.Background(), c, "invalid", "https://example.org", Request{Query: "test", Limit: 2})
	if errSource.Error != "invalid provider configuration" {
		t.Fatalf("%+v", errSource)
	}
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { _, _ = io.WriteString(w, `{"results":[]}`) }))
	defer ts.Close()
	providers := []struct{ name, endpoint string }{{"crossref", ts.URL}, {"openalex", ts.URL}, {"europepmc", ts.URL}}
	result := execute(context.Background(), ts.Client(), Request{Query: "valid", Limit: 1}, providers)
	if len(result.Results) != 3 || result.Results[0].Source != "crossref" || result.Results[2].Source != "europepmc" {
		t.Fatalf("%+v", result)
	}
	for _, r := range result.Results {
		if r.HTTPStatus != 200 || r.Error != "" {
			t.Fatalf("%+v", r)
		}
	}
}
func TestProtocol(t *testing.T) {
	client := &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader("{}")), Header: http.Header{}}, nil
	})}
	for _, test := range []struct {
		data  string
		valid bool
	}{
		{`{"query":"neural circuit","limit":2}`, true},
		{`{"query":"x","limit":2}`, false},
		{`{"query":"neural","limit":2,"url":"http://internal"}`, false},
		{`{"query":"neural","limit":2}{"query":"second","limit":2}`, false},
		{"{", false},
	} {
		var out bytes.Buffer
		err := run(strings.NewReader(test.data), &out, client)
		if (err == nil) != test.valid {
			t.Fatalf("%s => error %v", test.data, err)
		}
		if test.valid && !strings.Contains(out.String(), `"PROVIDER_STATUS_ONLY"`) {
			t.Fatalf("bad output: %s", out.String())
		}
	}
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }
func TestTimeout(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), time.Nanosecond)
	defer cancel()
	client := &http.Client{Timeout: time.Millisecond, Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) { return nil, fmt.Errorf("cancel: %w", ctx.Err()) })}
	status := single(ctx, client, "openalex", "https://example.org", Request{Query: "test", Limit: 2})
	if status.Error != "provider unavailable" {
		t.Fatalf("%+v", status)
	}
}

// These cases exercise the otherwise uncovered failure and CLI delivery paths.
type failingReader struct{}

func (failingReader) Read([]byte) (int, error) { return 0, errors.New("read failure") }
func TestReaderAndRequestConstructionFailures(t *testing.T) {
	client := &http.Client{Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: 200, Body: io.NopCloser(failingReader{}), Header: http.Header{}}, nil
	})}
	got := single(context.Background(), client, "crossref", "https://example.org", Request{Query: "good", Limit: 2})
	if got.Error != "provider body read failed" {
		t.Fatalf("%+v", got)
	}
	bad := single(nil, client, "crossref", "https://example.org", Request{Query: "good", Limit: 2})
	if bad.Error != "request setup failed" {
		t.Fatalf("%+v", bad)
	}
}
func TestServeMain(t *testing.T) {
	client := &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader("{}")), Header: http.Header{}}, nil
	})}
	var out, errOut bytes.Buffer
	if rc := serveMain(strings.NewReader(`{"query":"study","limit":1}`), &out, &errOut, client); rc != 0 {
		t.Fatalf("unexpected rc %v: %s", rc, errOut.String())
	}
	out.Reset()
	if rc := serveMain(strings.NewReader("x"), &out, &errOut, client); rc != 1 {
		t.Fatal("invalid request succeeded")
	}
	if !strings.Contains(errOut.String(), "invalid request") {
		t.Fatal("error not reported to stderr")
	}
}

// Redirects must never be followed to arbitrary origins.
func TestProviderRedirectsAreNotFollowed(t *testing.T) {
	calls := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		http.Redirect(w, r, "https://example.invalid/private", http.StatusFound)
	}))
	defer server.Close()
	client := &http.Client{CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}
	got := single(context.Background(), client, "crossref", server.URL, Request{Query: "valid", Limit: 1})
	if calls != 1 || got.HTTPStatus != http.StatusFound || got.Error != "provider returned non-200" {
		t.Fatalf("unexpected redirect: %+v, calls=%d", got, calls)
	}
}
