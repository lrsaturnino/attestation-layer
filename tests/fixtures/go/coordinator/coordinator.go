// Package coordinator is a small, non-trivial Go off-chain component used as the
// checked-in fixture for the Go source adapter vertical (PC-6/PC-7/PC-8).
//
// It is deliberately shaped so the call graph cannot be reconstructed lexically:
// Coordinate dispatches through the Stage interface, so the real edges
// (Coordinate -> Validator.Run and Coordinate -> (*Recorder).Run) are resolved
// by CHA over the type hierarchy, not by matching a callee name in the source.
// Two distinct types (Validator, Recorder) implement the same method name Run,
// which is Go's only symbol-resolution ambiguity source (Go has no overloads).
package coordinator

// Stage processes an amount and returns the amount handed to the next stage.
type Stage interface {
	Run(amount int) int
}

// Validator clamps a negative amount to zero before it flows downstream.
type Validator struct{}

// Run implements Stage for Validator.
func (Validator) Run(amount int) int {
	if amount < 0 {
		return 0
	}
	return amount
}

// Recorder accumulates the amounts that flow through it.
type Recorder struct {
	total int
}

// Run implements Stage for *Recorder, recording the running total.
func (r *Recorder) Run(amount int) int {
	r.total += amount
	return r.total
}

// Total reports the recorded running total.
func (r *Recorder) Total() int {
	return r.total
}

// Coordinate runs the redemption amount through every stage in order. The call
// to s.Run is an interface dispatch: CHA links it to every implementation of
// Stage, an edge a lexical pass cannot attribute to a concrete receiver.
func Coordinate(amount int, stages []Stage) int {
	out := amount
	for _, s := range stages {
		out = s.Run(out)
	}
	return out
}
