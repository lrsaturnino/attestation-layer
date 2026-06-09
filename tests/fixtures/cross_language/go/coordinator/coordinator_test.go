package coordinator

import (
	"context"
	"runtime/trace"
	"sync"
	"testing"
)

// TestSweepPipelineEmitsTrace exercises the coordinator under runtime/trace user annotations. Capture
// is driven by `go test -trace=<file>`, so the emitted runtime/trace carries goroutine-attributed,
// call-level events:
//
//   - a "sweep" task scopes the whole pipeline,
//   - the "authorize" and "sweep" regions name the two stages (operator authorization, then the
//     guarded sweep), and
//   - the work runs on a spawned goroutine so the task owner and the stage regions live on different
//     goroutines — the interleaving the adapter must preserve when it normalizes the trace.
func TestSweepPipelineEmitsTrace(t *testing.T) {
	ctx, task := trace.NewTask(context.Background(), "redeem")
	defer task.End()

	authorizer := NewAuthorizer()
	sweeper := &Sweeper{}

	var wg sync.WaitGroup
	var out int
	var ok bool
	wg.Add(1)
	go func() {
		defer wg.Done()
		const operator = "operator"
		trace.WithRegion(ctx, "authorize", func() {
			authorizer.Authorize(operator)
			trace.Logf(ctx, "stage", "authorize operator=%s", operator)
		})
		trace.WithRegion(ctx, "sweep", func() {
			out, ok = execute_sweep(authorizer, operator, 5, sweeper)
			trace.Logf(ctx, "stage", "sweep total=%d ok=%t", out, ok)
		})
	}()
	wg.Wait()

	if !ok {
		t.Fatalf("authorized sweep must succeed")
	}
	if out != 5 {
		t.Fatalf("want swept total 5, got %d", out)
	}
	if sweeper.Total() != 5 {
		t.Fatalf("want recorded total 5, got %d", sweeper.Total())
	}

	// An unauthorized operator must be refused: nothing is swept and ok is false — the off-chain
	// rejection the cross-language requirement names.
	denied := &Sweeper{}
	if swept, allowed := execute_sweep(NewAuthorizer(), "intruder", 9, denied); allowed || swept != 0 {
		t.Fatalf("unauthorized sweep must be refused, got swept=%d ok=%t", swept, allowed)
	}
}
