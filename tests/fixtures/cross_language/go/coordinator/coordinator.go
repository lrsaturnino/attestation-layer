// Package coordinator is the OFF-CHAIN half of the PC-13 cross-language capstone: a small Go
// redemption-sweep coordinator that authorizes an operator before it executes a sweep.
//
// A sweep runs ONLY out of an authorized state. execute_sweep consults the Guard before it sweeps and
// refuses (sweeps nothing, returns ok=false) when the operator is not authorized — the off-chain
// authorization guard the cross-language requirement names, real in the source, not modeled only. The
// reviewed S (RedemptionCoordinator.tla) is a human's TLA model of exactly this guarantee, validated
// to reproduce this package's REAL `go test -trace` runtime traces (PC-11).
//
// The guard call is an interface dispatch (execute_sweep -> Guard.Check), an edge CHA resolves to
// (*Authorizer).Check over the type hierarchy, not by matching a callee name lexically. execute_sweep
// is named in snake_case so it matches the requirement's action identifier across the adapter line.
package coordinator

// Guard decides whether an operator is authorized to sweep.
type Guard interface {
	Check(operator string) bool
}

// Authorizer authorizes only the operators it has been told about.
type Authorizer struct {
	allowed map[string]bool
}

// NewAuthorizer builds an Authorizer with no operators authorized.
func NewAuthorizer() *Authorizer {
	return &Authorizer{allowed: map[string]bool{}}
}

// Authorize marks an operator as allowed to sweep.
func (a *Authorizer) Authorize(operator string) {
	a.allowed[operator] = true
}

// Check implements Guard for *Authorizer.
func (a *Authorizer) Check(operator string) bool {
	return a.allowed[operator]
}

// Sweeper accumulates the amounts swept through it.
type Sweeper struct {
	total int
}

// record adds an amount to the running swept total.
func (s *Sweeper) record(amount int) int {
	s.total += amount
	return s.total
}

// Total reports the recorded swept total.
func (s *Sweeper) Total() int {
	return s.total
}

// execute_sweep authorizes the operator through the guard, then sweeps the amount. It returns
// (swept, ok): ok is false and nothing is swept when the operator is not authorized — the off-chain
// rejection of an unauthorized sweep.
func execute_sweep(guard Guard, operator string, amount int, sweeper *Sweeper) (int, bool) {
	if !guard.Check(operator) {
		return 0, false
	}
	return sweeper.record(amount), true
}
