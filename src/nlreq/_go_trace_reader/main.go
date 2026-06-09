// Command go_trace_reader parses a Go runtime/trace file and emits one JSON
// object per user-meaningful, goroutine-attributed event (task/region/log) as
// newline-delimited JSON on stdout.
//
// It is the Go-vertical analogue of nlreq._slither_driver: the runtime/trace
// binary format is parsed by the toolchain-version-coupled reader in
// golang.org/x/exp/trace (vendored, pinned in go.mod/go.sum), which the Python
// go_client cannot do itself. Scheduler / GC / syscall events are dropped — the
// documented runtime-trace -> call-level lossy normalization (see
// nlreq.models.NormalizedTrace). The goroutine id and the observed (linearized)
// order are preserved on every emitted event so the interleaving survives.
//
// A reader that cannot parse the trace (e.g. a format version newer than the
// pinned x/exp/trace supports) exits non-zero with the error on stderr, so the
// caller degrades to a non-extracted result rather than fabricating a trace.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"

	"golang.org/x/exp/trace"
)

type event struct {
	Ordinal   int    `json:"ordinal"`
	Kind      string `json:"kind"`
	Goroutine int64  `json:"goroutine"`
	TimeNs    int64  `json:"time_ns"`
	Name      string `json:"name"`
	Category  string `json:"category"`
	Message   string `json:"message"`
	Task      uint64 `json:"task"`
}

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: go_trace_reader <trace-file>")
		os.Exit(2)
	}
	f, err := os.Open(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	defer f.Close()

	r, err := trace.NewReader(f)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}

	enc := json.NewEncoder(os.Stdout)
	ordinal := 0
	var base trace.Time
	haveBase := false
	for {
		e, err := r.ReadEvent()
		if err == io.EOF {
			break
		}
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(2)
		}
		if !haveBase {
			base = e.Time()
			haveBase = true
		}
		out := event{
			Ordinal:   ordinal,
			Kind:      e.Kind().String(),
			Goroutine: int64(e.Goroutine()),
			TimeNs:    int64(e.Time().Sub(base)),
		}
		switch e.Kind() {
		case trace.EventRegionBegin, trace.EventRegionEnd:
			out.Name = e.Region().Type
			out.Task = uint64(e.Region().Task)
		case trace.EventTaskBegin, trace.EventTaskEnd:
			out.Name = e.Task().Type
			out.Task = uint64(e.Task().ID)
		case trace.EventLog:
			out.Category = e.Log().Category
			out.Message = e.Log().Message
			out.Task = uint64(e.Log().Task)
		default:
			// Drop scheduler / GC / sync / metric noise: only user-meaningful,
			// goroutine-attributed events survive the call-level projection.
			continue
		}
		if err := enc.Encode(out); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(2)
		}
		ordinal++
	}
}
