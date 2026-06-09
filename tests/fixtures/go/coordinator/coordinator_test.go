package coordinator

import (
	"context"
	"runtime/trace"
	"sync"
	"testing"
)

// TestRedemptionPipelineEmitsTrace exercises the coordinator under runtime/trace
// user annotations. Capture is driven by `go test -trace=<file>`, so the emitted
// runtime/trace carries goroutine-attributed, call-level events:
//
//   - a "redeem" task scopes the whole pipeline,
//   - the "validate" and "record" regions name the two stages, and
//   - the work runs on a spawned goroutine so the task owner and the stage
//     regions live on different goroutines — the interleaving the adapter must
//     preserve when it normalizes the trace.
func TestRedemptionPipelineEmitsTrace(t *testing.T) {
	ctx, task := trace.NewTask(context.Background(), "redeem")
	defer task.End()

	validator := Validator{}
	recorder := &Recorder{}

	var wg sync.WaitGroup
	var out int
	wg.Add(1)
	go func() {
		defer wg.Done()
		amount := 5
		trace.WithRegion(ctx, "validate", func() {
			amount = validator.Run(amount)
			trace.Logf(ctx, "stage", "validate amount=%d", amount)
		})
		trace.WithRegion(ctx, "record", func() {
			out = recorder.Run(amount)
			trace.Logf(ctx, "stage", "record total=%d", out)
		})
	}()
	wg.Wait()

	if out != 5 {
		t.Fatalf("want total 5, got %d", out)
	}
	if recorder.Total() != 5 {
		t.Fatalf("want recorded total 5, got %d", recorder.Total())
	}
}
