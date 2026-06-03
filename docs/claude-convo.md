ground and summary https://reubenbrooks.dev/blog/structural-backpressure-beats-smarter-agents/May 22Claude responded: Structural Backpressure Beats Smarter Agents — Reuben Brooks, May 18, 2026Fetched: Structural Backpressure Beats Smarter AgentsFetched: Structural Backpressure Beats Smarter AgentsStructural Backpressure Beats Smarter Agents — Reuben Brooks, May 18, 2026
Thesis. For a wide class of production software, structural backpressure beats incremental improvements in agent intelligence. The bottleneck isn't whether a model can write the code — it's whether you can know the code upholds the invariants you cared about. That knowledge has to come from the substrate, not from waiting for a smarter model.
The core distinction. Behavioral gates ("don't skip authorization," CLAUDE.md rules, system prompts) depend on the model and every future reviewer remembering and reapplying an invariant. Structural gates — compilers, type checkers, proof checkers — produce a concrete refusal about the artifact in front of them. That refusal is the point. It lets us move work out of the model's instruction space and into the substrate the model is building on.
The mechanism (Shen-Backpressure). Brooks built a tool around Shen, a small, statically-typed Lisp with a sequent-calculus type system. You write invariants once as Shen sequent rules (premises above a horizontal line, conclusion below), then shengen lowers them into guard types in the target language. The model writing Go or TypeScript never needs to know Shen exists. It needs the code to compile and the gates to pass.
Worked example: multi-tenant auth. The spec declares a proof chain jwt-token → authenticated-user → tenant-access → resource-access. Each datatype has premises that must be discharged to construct a value. In generated Go, fields are unexported and the constructor is the only path — there's no exotic trick, just ordinary visibility plus codegen. The handler then operates on a value that represents the already-traversed chain. The proof travels with the value. Skip the chain, pass a raw string, and the build fails before a binary exists.
Loop integration. sb loop runs a Ralph-style loop with five default gates: shengen (spec-to-guard drift), go test, go build, shen tc+ (spec consistency), and tcb audit (catches hand edits to generated code). Failures feed into the next prompt as concrete context. The harness is pluggable: Claude Code (claude -p) is the default; Cursor, Codex, and others work by setting RALPH_HARNESS. Go and TypeScript are full production targets; Python and Rust have reference emitters.
The honest limits. Specs cost effort to write and maintain. TCB now includes the Shen type checker, the generator, and the target compiler. The seal is only as strong as the host language's encapsulation — In Go, code inside the guard package could forge values; reflection and zero values are theoretically available as escape hatches. Brooks's claim is deliberately narrow: using shengen to lower spec proofs into the target language makes the specified invariants practically impossible to bypass by accident, not categorically impossible to bypass at all.
The closing move. Capability ≠ certainty. "The model is reliable" is a claim about the writer; "this artifact upholds the invariant" is a claim about the one object in front of you. And there's a regulatory angle: a spec + passing gates + green CI is something you can hand an auditor, where "we used a capable model" isn't.

This sits adjacent to a lot of your recent territory — Ralph loops, deterministic grading rubrics, the Merkle Hunt / Hermetic Vault benchmark designs. The interesting tension with your tBTC work is that Solidity already gives you a fairly strong structural gate (the EVM type system, plus tools like Slither, plus Foundry invariant tests), but the application-level invariants — "only the wallet owner can redeem after timeout," "deposits and withdrawals reconcile to the same SPV-proven Bitcoin state" — still mostly live as behavioral gates in prose and reviewer attention. The Shen-Backpressure pattern is essentially "make the application invariants type-system-enforced via codegen rather than convention," which is a more disciplined version of what well-architected smart contract codebases reach for with custom types and modifier patterns.Turn on web search in Search and tools menu. Otherwise, links provided may not be accurate or up to date.You said: what invarant meanswhat invarant meansMay 22Claude responded: An invariant is a property that must hold true always — across every state, every code path, every input — for the system to be considered correct.An invariant is a property that must hold true always — across every state, every code path, every input — for the system to be considered correct. Not "usually true," not "true if you remember to check" — true by construction.
Concrete examples:

In a multi-tenant API (the post's example): "a user can only access resources belonging to a tenant they're a member of." That must hold for every request, every endpoint, forever.
In tBTC: "total minted tBTC ≤ total BTC custodied in active deposits." If that's ever false, the system is insolvent.
In a sorted list: "for all i, list[i] ≤ list[i+1]." Any operation that breaks ordering breaks the invariant.

This is exactly what Foundry's invariant test mode targets — you declare a property, the fuzzer hammers random call sequences at your contract, and the test fails if any sequence produces a state where the property is false.
Brooks's point in the post is about where the invariant lives. The traditional approach puts it in:

A comment ("// don't forget to check tenant membership")
A code review checklist
A prompt to the model
A hand-written if at the top of every handler

All of those rely on someone — human or model — remembering to apply it correctly every time. A structural approach puts the invariant into the type system so that code which violates it doesn't compile. The invariant stops being a rule people follow and becomes a shape the code is forced into.You said: back to the article - eli5 what shen doesback to the article - eli5 what shen doesMay 22Claude responded: In the post, Shen is doing one job: it's the language you write the rules in.In the post, Shen is doing one job: it's the language you write the rules in.
Think of it as a tiny notation for writing "permission slips with prerequisites." You write things like:

To stamp this paper "tenant-access," you must first show me (1) an authenticated user and (2) proof they're a member of the tenant.

Shen's syntax — that horizontal line in the spec — is just a formal way of saying "the stuff above the line must be true before the thing below the line can exist." That's the whole conceptual move.
Why use Shen specifically and not, say, plain Go or TypeScript? Two reasons:

It's small and proof-shaped. Shen's type system is built on sequent calculus, which is literally the math notation for "given these premises, you can conclude this." So writing rules of the form "to construct X, you need Y and Z" is the native idiom. You're not fighting the language.
It's a single source of truth. You write the rule once in Shen, then shengen (the code generator) translates it into Go structs, or TypeScript classes, or Python, or Rust — whatever your real app is written in. The generated code uses ordinary language features (unexported fields, smart constructors) to make the rule unbreakable. The model writing your app never sees or touches Shen.

So the mental model is:
Shen spec  ──shengen──▶  Guard types in Go/TS
(the rule)              (the rule, enforced by the compiler)
Shen is the short, reviewable file where the invariants live. The hundreds of lines of generated guard code are the mechanical enforcement of those invariants. You audit the short file; the compiler audits the rest.
That's basically it. Shen isn't doing anything magical — it's a compact, precise notation for "here are the rules; please project them into my real codebase as types I can't accidentally violate."You said: how is it diffeent from tLA?how is it diffeent from tLA?May 22Claude responded: Really different tools doing really different jobs — they're often confused because both wear the "formal methods" badge, but they sit at different layers.Really different tools doing really different jobs — they're often confused because both wear the "formal methods" badge, but they sit at different layers.
TLA+ is a modeling language. You write a mathematical description of your system — its states, the actions that transition between states, and the temporal properties you want to hold ("the system never reaches a state where two nodes both think they're leader," "every request eventually gets a response"). Then a model checker (TLC) exhaustively explores reachable states, or a theorem prover (TLAPS) proves properties symbolically. The TLA+ spec lives parallel to your actual code. AWS uses it to design S3, DynamoDB, etc. before writing the production Java.
Shen-Backpressure is a projection tool. You write rules in Shen that get compiled into your actual implementation as types and constructors. The Go compiler then enforces them on every build. There is no separate model — the spec becomes part of the codebase.
Concrete differences:
TLA+Shen-BackpressureWhat it verifiesBehavior over time (state-space properties)Construction-time invariants on valuesHowModel checking or theorem provingOrdinary target-language type checkingConnection to codeNone — separate artifact, drift is a known problemGenerates the enforcement code directlySweet spotConcurrent protocols, distributed consensusAuthorization, capabilities, proof-chain invariantsVerification costMinutes to daysCompile timeWhere it sits in workflowDesign phaseInside the agent's edit-build-test loop
The deepest difference is the spec-implementation gap. In TLA+ you write a beautiful spec for Paxos, then you write Java that maybe implements that spec — and there is no machine-checked link between the two. The famous failure mode is the spec being correct, the code being wrong, and nobody noticing because they evolve separately. Shen-Backpressure is explicitly designed to eliminate that gap for the class of invariants it can express — the spec doesn't just describe the system, it generates the only path to constructing certain values.
The flip side: TLA+ can express things Shen-Backpressure can't touch. Temporal properties ("eventually X"), liveness, concurrency safety on shared mutable state, ordering of events across nodes — that's TLA+'s home turf. Shen-Backpressure can't say "in no execution does the leader change twice in one term." It can only say "you cannot construct a LeaderCommit without first showing me a quorum proof for this term."
For smart contracts: TLA+ is what you'd reach for to verify that your bridge protocol has no deadlock or double-spend reachable state across a sequence of attacker actions. Shen-Backpressure is what you'd reach for to make "this withdrawal is authorized" a thing that can't be constructed in Solidity without the signature, the merkle proof, and the timelock check all being present — enforced by the type system, not by reviewer attention.
They're complementary, not competitive. You could use TLA+ to design tBTC's redemption protocol and Shen-Backpressure-style codegen to make sure no Solidity handler accidentally bypasses the authorization chain when implementing it.You said: i still dont get what the article is proposingi still dont get what the article is proposingMay 23Claude responded: Let me strip it all the way down.Let me strip it all the way down. The actual proposal is one sentence:
Stop writing rules in prompts. Encode them as types the compiler refuses to violate, and put the compiler inside the agent loop.
That's it. Everything else — Shen, sequent calculus, shengen, the five gates — is implementation detail.
Here's the concrete picture. Today you probably do this:

Tell Claude Code "always check tenant membership before returning resources" (in CLAUDE.md, or the system prompt, or both)
Let it generate handlers
Review the PR, hope every handler has the check, hope nobody removes it next month

Brooks's proposal: do this instead.

Write a short file that says, in a formal notation: "To produce a value of type TenantAccess, you must first present an authenticated user AND a database-confirmed membership record."
Run a generator. It spits out Go (or TS) code where TenantAccess has private fields and exactly one constructor, and that constructor literally won't return a value unless both premises are present.
Hand that codebase to the agent. The agent writes handlers. If any handler tries to return resources without going through the proper construction chain, go build fails. The agent sees the failure and fixes it. If it tries to fake the value, the fields are unexported — also fails.
Wrap this in a Ralph-style loop where compile/test/codegen-drift/audit-of-generated-code are all gates that must be green to "finish."

The shift is from "the AI is responsible for remembering the rule" to "the codebase is shaped so the rule can't be violated by accident, and the loop refuses to stop until that's true."
Why he thinks this matters: people are spending a lot of effort trying to make agents smarter, more careful, better-instructed. Brooks is saying that's the wrong lever for production code. The cheaper, more durable lever is to change what the agent is writing against so that the existing models — which already can write almost any code — physically can't produce a binary that violates your core invariants. The agent doesn't need to remember; the type system remembers for it.
The Shen-Backpressure tool is just his packaging of this idea: a spec language + a code generator + a CLI that wires the gates into the agent loop. You could implement the same philosophy without Shen at all — hand-written smart constructors with unexported fields would get you 80% of the way. The tool exists to make the practice cheap enough to actually adopt.
That's the whole proposal.You said: ok got it - lets keep this spirit, but change subject:ok got it - lets keep this spirit, but change subject:I want to build a TLA+ like project
BUT I need it to be useful for validating natural language and semantics requests
like a human do
we have today cucumber as a tool for formal validation of requests
I need something better - TLA+ like
where semanctics turns to code-like validations and only when all arguments closes successfully it passesMay 23Claude responded: Good ambition.Good ambition. Let me push back on the TLA+ framing first because I think you're reaching for the wrong precedent, and then sketch what you're actually after.
TLA+ is the wrong analogy. TLA+ is for state-space exploration over time — "in no reachable state does X." What you're describing is closer to proof-carrying authorization (Appel, Felten, Lampson, Abadi, ~2000s) wedded to the Brooks pattern we just discussed. The shape is: a request is a proof obligation; the system refuses to act on it until every premise has been discharged. Cucumber is retrospective ("was the thing built right?"). What you want is prospective ("is this thing I'm being asked to do well-formed, complete, and authorized?"). Different verb, different abstraction.
The core move, stated in Brooks's language: the NL request itself becomes a value that cannot be constructed unless its premises close. Same trick, different layer.
The architecture, in four layers:
1. Spec language — the "rules of formation" for a class of request. Sequent-calculus-shaped, like Shen:
rule approve-purchase:
  premises:
    requester        : authenticated-employee
    amount           : positive-number
    vendor           : approved-vendor-for(amount, requester.dept)
    budget-available : has-remaining(requester.dept, amount, current-quarter)
    dual-control     : if amount > 10000 then countersigner exists
                       and countersigner ≠ requester
    no-conflict      : no-pending-purchase(vendor, requester, last-24h)
  ───────────────────────────────────────
  conclusion: valid-purchase-order(requester, vendor, amount)
This is the artifact a human reviews. It's short, it's the source of truth, and it's the thing that gets versioned and audited. The structure deliberately mirrors Shen's sequent rules so the "above the line must hold to construct what's below the line" intuition transfers cleanly.
2. Semantic parser — NL → structured claim(s). This is where LLMs earn their keep. The parser doesn't collapse ambiguity, it enumerates it. "Approve the Acme invoice" could mean three things; the parser returns all three as candidate claims with rough probabilities. Crucially, the parser's output is structured data, not free text. The downstream gate operates on the structure.
3. Premise-discharge engine — the closure check. For each premise in the rule, attempt to discharge it via one of:

Deterministic lookup (database, ACL, authority graph) — preferred whenever possible
Semantic check by LLM (only for premises that are inherently linguistic, like "is this vendor in the same product category as past approvals?")
Clarification request to human (premise unprovable from current context → return a structured "incomplete proof" naming exactly the missing premise)

The discharge engine is the analog of shengen + the build gate. Every premise is a separate gate. Failure of any one means the request cannot be constructed into an actionable form.
4. Refusal surface — the only path to action. Downstream systems accept only fully closed proofs. Just like Brooks's unexported fields: there is no constructor for ApprovedPurchaseOrder that doesn't take all premises as arguments. An LLM agent cannot "decide" to act on a request whose proof didn't close. The action API physically doesn't accept it.
What this gives you that Cucumber doesn't:
Cucumber asserts behavior ("when X, then Y"). This asserts well-formedness of intent. Cucumber catches "the code is wrong"; this catches "the request is incomplete, ambiguous, unauthorized, or unsafe — refuse before any work begins."
The hard problems, named honestly:

The parser is the weak link. NL → structured claim is where LLM fallibility re-enters. Mitigation: multi-pass parsing with disagreement detection. If two parses give different premise sets, refuse and ask. Treat parser disagreement as itself a premise that must discharge.
Premise specification is the real work. Same as Brooks's "writing the spec is not free." Most of the value comes from having spent the discipline to write down "what does it actually mean for this request to be valid?" — which most teams have never done explicitly.
The discharge LLM can hallucinate premise satisfaction. Mitigation: any premise discharged via LLM rather than deterministic lookup is marked as such in the proof object. A second LLM (different model, different prompt, structured rubric) audits LLM-discharged premises. The audit is itself a gate. This is the Ralph loop's deterministic-grading-rubric pattern applied at the request layer.
Premises that require world knowledge are unbounded. "Is this vendor reputable?" doesn't have a clean discharge. Solution: don't allow such premises. Force them into the deterministic layer ("vendor must be on the pre-approved list") or out of scope entirely.
Specs drift from reality. Same problem TLA+ has. Mitigation: log every refused request and every clarification round-trip. Patterns in refusals are signal that the spec is wrong, not that requests are wrong. Build the feedback loop in from day one.

Concrete starting point:
Pick one workflow where you already know the invariants — procurement approval, customer refund, deployment authorization, anything with a clear "rules of who can ask for what" shape. Write the spec in ~20 lines of your sequent-shaped DSL. Build the four layers minimally:

Parser: one LLM call with structured output (JSON schema for the claim type)
Discharge: 80% database lookups, 20% LLM checks with audit
Refusal: a single "approved proof object" type that downstream code accepts

Run it against a corpus of real past requests. Measure: what % closed cleanly? What % required clarification? What % were refused-correctly vs refused-incorrectly? The ratio of "refused-incorrectly" tells you whether the spec is too tight or the parser is too brittle.
The genuinely novel contribution here, if you build it, is the closure-as-action-gate pattern: not "the LLM read the request and decided to act," but "the request became a proof, the proof closed, and the action ran because the proof closed." That's the part nobody is doing well yet, and it's the part that matters most as agents start taking real actions on real systems.
You'd basically be building the input-side counterpart to your Attestation Layer work. The attestation layer makes outputs verifiable; this makes inputs verifiable. Together they bracket the agent with structural gates on both ends.You said: i was refering to TLA+ like, like Specula tool, because the requirements MUST also fit with legacy potential code, and legacy code is verified with TLA+, so we…i was refering to TLA+ like, like Specula tool, because the requirements MUST also fit with legacy potential code, and legacy code is verified with TLA+, so we must come up with determinicly vet a semantic statement against the current codebase and againt itselfMay 23Claude responded: Let me look up Specula to make sure I'm thinking about the same tool you are.Let me look up Specula to make sure I'm thinking about the same tool you are.Searched the webSearched the webGood — now I see what you're after, and it's a sharper and harder problem.
What Specula actually does (so we're aligned): it's a multi-phase agentic workflow that goes code → LLM → candidate TLA+ spec, then uses Control Flow Analysis for structural correctness and trace validation to ensure the spec semantically matches the real implementation, then runs model checking to find invariant violations. The crucial insight they had — and this matters for your problem — is the failure mode they identified: when you ask an LLM to spec etcd's Raft, it produces something syntactically clean that passes the TLA+ parser, but on inspection it's the spec from the Raft paper appendix, not a spec of etcd's actual code. Trace validation is what closes that gap: the spec must reproduce real execution traces, or it's not really a spec of this system. GitHubACM SIGOPS
What you want is the inverse direction: not Code → Spec, but NL Requirement → Formal Claim → checked-against-existing-Spec. With a closure gate: the requirement is refused unless every check passes.
Let me sketch what that pipeline looks like, borrowing Specula's architectural moves but inverting the flow:
1. Requirement DSL (input layer). Don't accept raw NL. Force a semi-structured shape — call it Gherkin++ — that the LLM has a fighting chance of translating reliably. Free-form "the system should be fast" is rejected at the gate; "any request to endpoint /redeem must complete within 500ms p99 when concurrent_redemptions < 100" is accepted. The DSL constrains ambiguity at the source.
2. NL → TLA+ fragment (the translator). LLM produces a formal projection of the requirement. This is the Specula moment but inverted: instead of code → spec, requirement-text → spec-fragment. Run this multiple times with different prompts/models. If the resulting fragments aren't logically equivalent (check via TLAPS), refuse and emit the disagreement back to the requester as a clarification question. Disagreement among translators is itself a signal that the requirement is ambiguous.
3. Self-consistency check. Is the translated fragment internally consistent? Run TLAPS or Apalache on the fragment alone. Catches contradictions hidden in the NL ("must always X" and "must never X under condition Y" where Y is always true).
4. System-consistency check — this is the actual core. Given the existing TLA+ spec S (the legacy system's verified model) and the new requirement R, check satisfiability of S ∧ R. Three outcomes:

Satisfiable, no invariant violated: R is compatible with the existing system as specified.
Counterexample found: Apalache produces a concrete trace where S ∧ R violates an existing invariant I_k. The output names exactly which invariant, which states, and which actions. This is the proof that R is incompatible — and it's actionable.
Timeout / undecided: state-space exploration didn't terminate. Mark R as "unverified-compatible" with explicit confidence label. Don't silently approve.

5. Trace validation against current behavior (the Specula move). For the modules affected by R, replay real execution traces from the current codebase against the formalized R. Three outcomes:

All traces satisfy R → R is already implicitly implemented (just needs documenting).
Some traces violate R → quantify the delta. R requires code change in these specific flows.
No traces touch the affected behavior → coverage gap; R cannot be empirically validated and needs careful symbolic-only review.

6. Delta extractor. Structured output naming exactly: which TLA+ invariants need to be added, which actions in the spec need new pre/post-conditions, which code modules will need changes, which existing tests will break. This is what a senior engineer would produce in a design review — except mechanically, so it's auditable and reproducible.
7. Closure gate. R becomes an "approved requirement" — flowable into your backlog / PR pipeline — only when (2)-(5) all close green. Otherwise structured refusal with exactly what's missing or contradicted.
The honest hard parts:
Spec coverage. Real codebases have TLA+ coverage for maybe 10-20% of their behavior. Most requirements will touch unspecified regions. You'd want Specula (or something like it) running continuously to expand spec coverage as a precondition for accepting requirements that touch unspecified areas. Spec coverage becomes a tracked metric, like test coverage, and requirements are rejected against under-specified modules until the spec is filled in.
State-space explosion. S ∧ R model checking will hit blowup constantly. Apalache (symbolic) helps; bounded model checking helps; compositional verification helps. You will need an explicit "verification budget" per requirement and an explicit "unverified-but-not-refused" category.
NL → TLA+ is a research-grade translation problem. The DSL constraint helps a lot but doesn't eliminate it. The Specula trick — multiple translation attempts + structural validation + semantic validation against traces — applies here too. Treat the translator as untrusted and gate it with checks that are themselves deterministic.
Spec drift. If the underlying code evolves and the TLA+ spec doesn't, your gate is checking against fiction. This is the classic TLA+ problem and the reason Specula exists. You'd want trace validation running continuously as a CI gate: any drift between code behavior and spec → block merges until spec is updated.
The Brooks-style framing of all this: you're trying to make "well-formed requirement consistent with the verified system" a value that cannot be constructed without discharging every premise. The premises happen to require model checking, trace validation, and multi-pass LLM translation rather than smart constructors — but the shape is the same. Closure or refusal. No middle ground.
Concrete starting point for you specifically: pick one bounded subsystem where you already have a clean TLA+ spec — there are decent published ones for Raft, Paxos, two-phase commit, and several DeFi-adjacent protocols. Build the pipeline against that subsystem. Don't try to handle "any requirement against any codebase" on v1. Pick one verified protocol, build the requirement gate around it, prove the loop closes, then expand. If you can take a real GitHub-issue-style requirement against a Raft implementation and have your tool produce either (a) a closed proof of consistency or (b) a concrete counterexample naming which invariant breaks — you have something genuinely new.
This is the input-side analog of what Specula does on the output side, and as far as I can tell from current public work, nobody is doing it as a closure-gated pipeline yet.You said: spec etcd's Raft?spec etcd's Raft?May 25Claude responded: Quick unpacking of that reference, since it landed without context:Quick unpacking of that reference, since it landed without context:
etcd is a distributed key-value store written in Go. It's the storage backbone of Kubernetes — every piece of cluster state (which pods exist, where they run, what their config is) lives in etcd. So "etcd is correct" is load-bearing for a huge fraction of cloud infrastructure.
Raft is the consensus algorithm etcd uses to keep multiple etcd nodes in agreement when some can fail or partition. Designed by Ongaro and Ousterhout (Stanford, 2014) explicitly as a more-understandable alternative to Paxos. The Raft paper is short, clean, and famously comes with a TLA+ spec in its appendix.
"Spec'ing etcd's Raft" means: write a TLA+ specification that accurately describes the behavior of etcd's actual Raft implementation. Not the algorithm in the paper — the code in github.com/etcd-io/etcd/raft.
That distinction is the whole point of the Specula anecdote. Paper-Raft is an idealized algorithm: leader election, log replication, safety. etcd's Raft is the production reality: pre-vote phase, learner nodes, configuration change protocols, joint consensus, snapshots, batching optimizations, specific timeout tuning, lease-based reads, ten years of accumulated bug fixes for edge cases the paper never mentioned. They share a name and a family resemblance, but they are not the same system. Bugs hide in the delta.
When the Specula team asked an LLM to spec etcd's Raft, the LLM produced something syntactically clean that passed the TLA+ parser — but it had essentially reproduced the spec from the paper's appendix (which is in training data), not a spec derived from etcd's actual code. So if you'd model-checked it, you'd be checking that the algorithm from the paper is correct (already known), not that etcd's implementation matches its intent (the actual question). The trace validation step in Specula exists specifically to catch this: a spec only counts if it can reproduce real execution traces from the actual binary.
Why this matters for your domain: the exact same failure mode exists in DeFi. There's "Uniswap v3 the AMM design" and there's UniswapV3Pool.sol. There's "the tBTC bridge protocol" and there's the deployed contracts with all their specific decisions, optimizations, governance hooks, and post-incident patches. If you asked an LLM to spec "the tBTC bridge," there's a high chance it would produce something that describes the white paper, not the contracts. The same trace-validation discipline applies: ground the spec in actual on-chain transaction traces, or you're checking the wrong artifact.
This is exactly why the inverse pipeline we just sketched needs trace validation as a non-negotiable step. Without it, your "consistency check against the existing system spec" is checking consistency against a fiction the LLM produced from training data, not against the system that actually runs.You said: TLAPS?TLAPS?May 25Claude responded: TLAPS = the TLA+ Proof System.TLAPS = the TLA+ Proof System. It's the interactive theorem prover for TLA+, developed by INRIA and Microsoft Research.
The TLA+ ecosystem has three verification tools, each with a different tradeoff:
TLC is the original model checker. Explicit-state, exhaustive. You give it bounded parameters (e.g., "up to 4 nodes, up to 10 messages in flight") and it brute-force explores every reachable state and checks your invariants. Concrete, easy to use, but limited to finite/bounded models. Most TLA+ users live here.
Apalache is a symbolic model checker. Instead of enumerating states, it encodes the state-space as SMT formulas and asks a solver (Z3) "is there any trace of length ≤ k that violates this invariant?" Handles much bigger state spaces than TLC for bounded-depth queries. This is what I'd reach for in your requirement-consistency pipeline because it's the one that produces actionable counterexamples cheaply at scale.
TLAPS is different in kind. It's an interactive proof assistant — you write a hierarchical proof of your spec's properties, step by step, and TLAPS dispatches each step to backend provers (Zenon for first-order logic, Isabelle for higher-order, SMT solvers for arithmetic). When the proof checks, you have unbounded guarantee: the property holds for any number of nodes, any number of messages, forever. Model checkers can only tell you "no violation up to bound k." TLAPS tells you "no violation, full stop."
The cost is that TLAPS requires significant human guidance. You don't push a button and get an answer; you write the proof outline, and TLAPS verifies your reasoning is sound. A serious TLAPS proof of a non-trivial protocol can take weeks of expert effort. AWS used TLC heavily for S3/DynamoDB; only a handful of teams in the world use TLAPS in production (the Tendermint/Cosmos consensus work is one of the more visible examples).
Practical rule for your tool: use Apalache as the workhorse for the consistency-check gate (fast, gives counterexamples), and reserve TLAPS only for invariants so load-bearing that you want machine-checked unbounded proofs — the equivalent of "this property must hold for tBTC for any number of redemptions, ever." Model checking finds bugs; theorem proving certifies absence of them. Both have a place; the cost ratio is roughly 100x.You said: "inverse direction: not Code → Spec, but NL Requirement → Formal Claim → checked-against-existing-Spec."inverse direction: not Code → Spec, but NL Requirement → Formal Claim → checked-against-existing-Spec."what spec means>May 25Claude responded: Good — "spec" is dangerously overloaded and I should have pinned it down.Good — "spec" is dangerously overloaded and I should have pinned it down. In that sentence, I specifically meant a formal mathematical model of the existing system, written in TLA+ (or an equivalent logic that supports automated checking).
The word "spec" gets used for at least five different things in software, and they are not interchangeable:

Informal docs — a Markdown file explaining what an API does. Human-readable, not machine-checkable. ("The spec says we should return 200.")
Interface contracts — OpenAPI files, TypeScript .d.ts, protobuf definitions. Machine-readable types and shapes, but they only check signatures, not behavior.
Behavioral test specs — RSpec, Cucumber features. Concrete scenarios written in a structured form, executed empirically.
Formal mathematical specs — TLA+, Z, B, Alloy, Coq. A complete logical model of the system's states, transitions, and the properties that must hold across them. Machine-checkable via model checkers or theorem provers.
Requirements specs — IEEE-style "the system shall..." documents. Human-written, prose, often the starting point for everything else.

When I wrote "checked-against-existing-Spec," I meant category 4 specifically — the same kind of artifact Specula produces from etcd's code. Concretely, a TLA+ spec is a .tla file that declares:

State variables (VARIABLES log, currentTerm, votedFor, state for a Raft node)
Initial state predicate (what's true at startup)
Actions — the allowed transitions and their preconditions/effects (AppendEntries(i, j) == ...)
Invariants — properties that must hold in every reachable state (AtMostOneLeaderPerTerm)
Temporal properties — properties that must hold across executions (Eventually(LeaderElected))

The crucial distinguishing property: a formal spec is a closed mathematical object you can run a solver against. You can ask it questions like "is there any reachable state where two leaders exist in the same term?" and get back either a proof of "no, never" or a concrete counterexample trace showing exactly how it could happen. You cannot ask that question of an OpenAPI file or a Markdown doc or a Cucumber feature.
So when the pipeline says "checked-against-existing-Spec," it means: take the new requirement, formalize it as a TLA+ fragment R, and ask Apalache "is the conjunction (S ∧ R) satisfiable without violating the existing invariants in S?" The answer is mathematical, not advisory.
The practical catch for your project: most production systems don't have a category-4 spec. They have category 1 (docs), category 2 (OpenAPI/types), and category 3 (test suites). Whether your tool can run at all depends on either (a) the team having invested in a TLA+ spec already, or (b) bootstrapping one with Specula or hand-writing one as part of adopting your tool. This is why I said earlier that "spec coverage" becomes a tracked metric like test coverage — and why your tool probably needs to gracefully degrade for modules without formal coverage rather than refusing every requirement that touches uncharted territory.You said: "Spec coverage."Spec coverage. Real codebases have TLA+ coverage for maybe 10-20% of their behavior. Most requirements will touch unspecified regions. You'd want Specula (or something like it) running continuously to expand spec coverage as a precondition for accepting requirements that touch unspecified areas. Spec coverage becomes a tracked metric, like test coverage, and requirements are rejected against under-specified modules until the spec is filled in."
How to know where a new feature will touch in a brownfield app? If certain areas are not speced, and we need it to be speced, it should run specula-like (or even specula first) in the area, before running my tool.
what you mean by "State-space explosion."?
what if I run my tool in a brand new app development? there's no legacy app, I'm requiring it vet NL from a brand new app.
what is DSL?
"NL → TLA+ is a research-grade translation problem." -> try research for similar works and studies in the field. Not TLA per se, by similar and/or same direction solutions.
"Spec drift. If the underlying code evolves and the TLA+ spec doesn't, your gate is checking against fiction." -> maybe a constant TLA+ specing should be kept running against the code, and we should have an automated, version control way to know whether this is up to date or not.Show moreMay 25Claude responded: Good battery of questions.Good battery of questions. Let me work through them in order, and I'll actually do the research search you asked for rather than answer from memory.
1. How to know where a new feature touches in a brownfield app
This is the code impact analysis problem, and you want a multi-layered approach:
Deterministic layer (cheap, accurate within scope):

Static call-graph analysis — start from the symbols mentioned in the requirement (entities, endpoints, types) and walk transitive callers/callees. Language servers (LSP) and tools like gopls, rust-analyzer, Solidity's static analyzers all expose this.
Module dependency graphs — at the package level, which modules import which.
For TLA+ specifically: maintain a code-to-spec mapping manifest — a file declaring which spec modules cover which code modules. This is metadata you keep alongside the spec.

Semantic layer (LLM, fuzzy):

Give the requirement to an LLM with a structured index of your codebase (file summaries, module purposes, API surface). Ask it to enumerate likely-affected modules with confidence scores.
Cross-validate against the deterministic layer. If the LLM says "this touches the redemption pipeline" and the call graph shows no path between requirement entities and redemption code, flag the disagreement.

Coverage layer:

Run the deterministic + semantic layers, get the union of affected modules.
Cross-reference against the code-to-spec manifest.
Modules with no spec coverage → those need to be spec'd first.
Practical pipeline: requirement → impact set → spec gap check → if gaps, queue Specula runs on those modules → only then run your gate.

This is essentially the same pattern test-coverage tools use, just one level up. The brownfield case is genuinely harder than greenfield (see below) but it's tractable with the right pipeline architecture.
2. State-space explosion
Combinatorial blowup in model checking. For a system with N state variables each with k possible values, the reachable state space is in the worst case k^N. Add concurrency and you multiply by all possible action interleavings.
Concrete example: a 3-node Raft cluster, each node with a log of up to 10 entries, 4 possible terms, 3 possible roles, plus in-flight messages. Naively that's millions of states. Try to model-check "no two leaders in the same term ever" by exhaustive enumeration and TLC will chew on it for hours or run out of memory entirely.
Why it bites your tool specifically: when you check S ∧ R for satisfiability, the solver has to reason about the combined state space of both the existing system and the new requirement's constraints. The intersection can be much larger than either alone, especially if R touches variables that interact non-trivially with existing actions.
Mitigations (in increasing order of effort):

Bounded model checking with explicit limits — "no violation in any trace of length ≤ 30." Cheap but only catches shallow bugs.
Apalache's symbolic encoding — handles much larger state spaces because it reasons about classes of states rather than enumerating them. Default choice for production.
Compositional verification — verify subsystems independently with assume-guarantee contracts. Hard to set up, scales much better.
Abstraction refinement — start with a coarse model, only refine where counterexamples need it (CEGAR loop). Research-grade but very powerful when it works.
Refuse to check beyond budget — set a per-requirement verification budget. If S ∧ R doesn't close within it, mark R as "unverified" and require human review. Honesty beats fake certainty.

For tBTC: imagine checking "no double-redemption is ever possible" with N deposits, M operators, and arbitrary network reorderings. That's the state space you're up against, and why Apalache + careful bounding matters.
3. Greenfield case
Honestly easier in most ways. No spec drift (because you're writing spec and code together), no legacy code archaeology, no Specula-style retroactive spec extraction. You also don't need code-to-spec mapping manifests because you can establish them as you go.
The pipeline shape changes:
NL requirement → formal claim → check internal consistency
              → check against accumulated spec so far
              → if approved: append to spec, become a constraint code must satisfy
              → code is then written to satisfy the accumulated spec
              → trace validation confirms code-spec alignment continuously
This is essentially spec-first development with an automated requirements gate. The spec grows organically with the system. Each new requirement is checked for consistency with everything already specified before it's accepted. The closure gate is structurally identical; the inputs are simpler.
The hard part shifts to: bootstrapping the initial spec, and convincing developers to maintain spec rigor when there's no legacy pressure forcing them to. This is a cultural problem more than a technical one. The technical advantage is significant — every check runs against ground truth (the spec) rather than against a possibly-drifted model of an existing system.
A genuinely interesting positioning: your tool could be marketed as "spec-driven development tooling for AI-coded greenfield projects" — pitched at teams already using Claude Code / Codex / Cursor for new builds, who want structural backpressure (Brooks's point) extended all the way up to the requirements layer. That's a much cleaner sell than "retrofitting formal methods into a brownfield codebase," which is famously a graveyard market.
4. DSL
Domain-Specific Language — a programming or markup language designed for a narrow problem domain rather than general computation. Examples:

SQL — DSL for relational queries
Gherkin — DSL for BDD scenarios (Given/When/Then)
HCL (Terraform) — DSL for infrastructure declaration
Solidity — DSL for EVM smart contracts (debatable, it's pretty general-purpose now)
TLA+ — DSL for formal specification
Shen (in Brooks's tool) — DSL for proof-shaped invariants

In my context: I'm proposing your input layer be a DSL for requirements, not raw natural language. Something like Gherkin's structure but with stronger semantic constraints — perhaps a small grammar that forces requirements into shapes the LLM can reliably translate. You'd be designing this DSL specifically to maximize the probability of correct NL → formal translation. The narrower the input grammar, the more reliable the translation.
5. NL → formal: actual research search
Let me do this properly.Searched the webSearched the webLet me do one more targeted search since you specifically mentioned vetting requirements against themselves:Searched the webSearched the webNow back to your questions:
5 (continued). NL → formal: the research landscape
There's significantly more active work here than I initially conveyed. The convergent patterns across the field validate the architecture we sketched, and a few specific projects map almost directly to pieces you'd want.
nl2spec (Hahn et al., 2023) does interactive NL → Linear Temporal Logic translation. Their key methodological contribution: they utilize LLMs to map subformulas of the formalization back to the corresponding natural language fragments of the input, so users can iteratively add, delete, and edit these sub-translations to amend erroneous formalizations. The bidirectional mapping (formal ↔ NL fragments) is exactly the affordance you'd want for clarification dialogues in your tool. arxiv
Req2LTL with OnionL (Ma et al., Dec 2025) is the most directly relevant recent work. It introduces a novel intermediate representation OnionL, which decomposes requirements into a compositional tree composed of semantic scopes, logical relations, and atomic propositions, thereby enabling structured and verifiable translation. By combining LLMs for hierarchical semantic decomposition with a deterministic, rule-based translator for validation and LTL conversion, REQ2LTL achieves 88.4% semantic accuracy and 100% syntactic correctness on real-world aerospace requirements, substantially outperforming prior approaches. The two-stage NL → intermediate → formal pattern is the established winning architecture. Don't translate end-to-end. arXiv
ALICE (Gärtner & Göhlich, 2024) does exactly the internal-consistency check you mentioned. It's an automated contradiction detection system tailored for formal requirements expressed in controlled natural language, integrating formal logic with LLMs. Methodology: a decision tree model addressing seven critical questions to ascertain the presence and type of contradictions, built on an expanded taxonomy of contradictions. On a real-world electric bus project they report 99% accuracy and 60% recall. Note the recall number — they catch a lot but miss a meaningful fraction. The hybrid (LLM + formal logic) approach outperforms LLM-only by a large margin. ACM Digital Library + 2
VERIFYAI (CEUR 2025) is closest in spirit to your overall pipeline. Natural language requirements and domain ontologies form the input, grounding the LLM in the target context. Different prompt strategies shape how inputs are presented for specification generation. Outputs are stored in a tool-neutral intermediate format (JSON-LD), which can be translated into the syntax required by verification tools. These tools check the generated specifications, while symbolic reasoning provides constraint-based feedback that helps refine them. Human reviewers remain part of the loop. CEUR-WS.org
Other relevant work to know about:

Lang2LTL (Liu et al., 2022) — NL → temporal specs for robotics
nl2postcond (Endres et al., 2023) — NL intent → program assertions/postconditions, with explicit metrics for discriminative power of generated specs
Meng et al. (Wiley Systems Engineering, Feb 2026) — interactive NL → logical formalism designed for non-experts
I/O Grammars (ASE 2025) — applied to translating Internet RFCs into executable protocol specs for testing
Hierarchical Semantics Decomposition (Ma et al., 2025) — same group as Req2LTL, broader methodology paper

Convergent patterns across all of this:

Intermediate representations are non-negotiable. OnionL, JSON-LD, controlled NL, structured trees. End-to-end NL → formal translation doesn't work well; everyone who's tried has retreated to a two-stage pipeline.
Hybrid LLM + symbolic always beats LLM-only. Often by a lot. The LLM does semantic decomposition; deterministic logic does conversion and validation.
Controlled Natural Language (CNL) at the input is accepted. Pure free-form NL is too ambiguous; everyone gates the input.
Interactive refinement is standard. Translate, show the user, let them correct, re-translate. No one assumes one-shot correctness.
The state of the art is ~88% semantic accuracy on well-structured domains (aerospace requirements). It's not a solved problem.

What's novel in your proposal vs. all of the above: none of this work specifically tackles the consistency check against an existing verified system spec. They all stop at "produce a formal spec from the requirement." You'd be composing the established translation pipeline (Req2LTL-style) with the consistency-check-against-existing-system pipeline (Apalache on S ∧ R). That composition, with closure-as-action-gate, is the contribution that doesn't exist yet as far as the literature shows.
Realistic positioning: Req2LTL gives you the translator. ALICE gives you the contradiction taxonomy. VERIFYAI gives you the pipeline shape. Specula gives you the spec extraction for brownfield. Apalache gives you the symbolic check. You'd be the integration, with the structural-backpressure framing as the core thesis.
6. Spec drift mitigation — your intuition is exactly right
The pattern you described is the right one and matches what mature formal methods practice has converged toward. Concretely:
Treat the spec as a versioned, freshness-tracked artifact alongside code. Both live in the same repo. PRs that touch certain code modules without touching the corresponding spec modules are flagged. PRs that touch spec without trace-revalidating are flagged.
Continuous trace validation in CI. Every commit:

Identifies which code modules changed (git diff, simple)
Looks up which spec modules cover those code modules (the manifest)
Re-runs trace validation: does the spec still reproduce execution traces from the new code?
If yes → spec is still fresh. If no → block merge until either spec is updated or the discrepancy is explicitly approved.

Hash-based freshness invariant. Each spec module carries a hash of the code modules it covers, computed at last successful trace validation. CI computes current hash of those code modules; if they differ and trace validation hasn't been re-run successfully, the spec is marked stale. This is essentially Cargo.lock semantics applied to formal specs.
Spec lag metric. Per module, track: time since last successful trace validation, number of code commits since last validation, percentage of executions covered by current traces. This becomes a dashboard metric and a CI gate threshold ("no module may be more than 30 commits stale before requirements against it are blocked").
The continuous Specula-like runner. As you suggested — run a Specula-style extraction continuously on changed modules to propose spec updates. The proposed updates are PRs that humans review and merge. The system never silently updates the spec (that would defeat the point), but it removes the manual burden of writing the update from scratch every time.
Putting all the pieces together, the system you're describing looks like:
Requirement (NL)
  ↓ DSL gate (input shape check)
  ↓ Req2LTL-style translator (NL → intermediate → formal R)
  ↓ Self-consistency check (ALICE-style + TLAPS/Apalache on R alone)
  ↓ Impact analysis (which modules does R touch?)
  ↓ Spec coverage check (are those modules speced? freshness?)
      ↳ if not: queue Specula run, block until spec catches up
  ↓ System consistency check (Apalache on S ∧ R)
      ↳ counterexample? refuse with structured "this would violate I_k via trace T"
  ↓ Trace validation (do current execution traces violate R?)
      ↳ if so: structured delta showing which flows need to change
  ↓ Closure gate: all green → R becomes an approved requirement
                              with attached proof object
                              that flows into the PR/backlog system

Continuously in CI:
  - Spec freshness check per module (hash-based)
  - Trace validation per commit on affected modules
  - Spec lag metric per module
  - Continuous spec-extraction proposals from Specula
That's a real, buildable system. The pieces all exist in research; the integration is the contribution. It's research-grade but achievable — exactly the kind of thing that pairs well with your existing harness-engineering and deterministic-grading instincts. The "Wanabai" / Attestation Layer framing of your earlier papers fits this naturally: you're extending the attestation surface backward, from "verify model outputs" to "verify the requirements the model is acting on." Same philosophy, new layer.You said: i liked it:i liked it:Realistic positioning: Req2LTL gives you the translator. ALICE gives you the contradiction taxonomy. VERIFYAI gives you the pipeline shape. Specula gives you the spec extraction for brownfield. Apalache gives you the symbolic check. You'd be the integration, with the structural-backpressure framing as the core thesis.is all project open sourced or have clear article written for consuption?May 25Claude responded: Good question.Good question. Let me check each one for source availability and accessible writing.Searched the webSearched the webMixed — let me give you the honest breakdown by readiness tier.
Production-grade open source with full docs (you could use these tomorrow):

Apalache — fully open source at github.com/apalache-mc/apalache. Active project, Docker images, comprehensive user manual, tutorials. Translates TLA+ into the logic supported by SMT solvers such as Microsoft Z3. Can check inductive invariants for fixed or bounded parameters and check safety of bounded executions. Used in production by Informal Systems for Tendermint/Cosmos consensus work. Has both an OOPSLA 2019 paper and practitioner docs. This is the most battle-tested piece in the stack. Note: currently not funded by any organization — it's de-facto funded by maintainers Igor Konnov, Jure Kukovec, and Thomas Pani. Sustainability risk worth knowing about. GitHubGitHub

Open source research prototypes (working code, recent, less battle-tested):

Specula — open source at github.com/specula-org/Specula. Won the 2025 TLA+ Foundation challenge sponsored by NVIDIA. Has step-by-step usage docs, demonstrated on etcd's Raft (Go) and Asterinas's SpinLock (Rust). The SIGOPS blog post (sigops.org/2026/can-llms-model-real-world-systems-in-tla) is excellent consumable writing — explains the methodology, the failure modes they hit, and why trace validation matters. Honest about limitations. Read the SIGOPS post before the repo; it's the better introduction.
Req2LTL / OnionL — open source at github.com/Meng-Nan-MZ/Req2LTL. Has a demo video, click-through workflow (NL → ONIONL → CHECK → MERMAID visualize → ONIONL → LTL), and feedback loop for incorrect translations. Paper at arxiv 2512.17334 from December 2025. Very recent — code works but expect rough edges, limited test coverage beyond the aerospace benchmark. The architecture is what matters most; even if you don't use their code directly, the two-stage NL → intermediate-tree → LTL pattern is the contribution. GitHub

Published methodology, code not obviously public:

ALICE — papers are open access (Springer "Automated Software Engineering" 31(2), 2024; Design Society Proceedings 2024). The methodology is described in enough detail that re-implementation is feasible — they document the seven-question decision tree, the contradiction taxonomy, the LLM prompts. Datasets are partially accessible: 210 anonymized requirement pairs from the electric bus project are provided; Dataset 2 with 1071 manually-labeled pairs available for validation. I couldn't find an open code repository in my search. The PhD dissertation by Gärtner (TU Berlin, depositonce.tu-berlin.de) collects the three-paper progression and is freely downloadable — that's the best single read. ResearchGate
VERIFYAI — CEUR paper (ceur-ws.org/Vol-4142/paper11.pdf) is open access. Pipeline architecture is described but I haven't found a public code drop. Treat this as a reference architecture rather than a tool — it's most useful for the modular design pattern (LLM + ontology + JSON-LD intermediate + verification tool plug-ins).

Bonus that's worth mentioning:

nl2spec (Hahn et al., arxiv 2303.04864, 2023) — they explicitly mention an open-source implementation including a web-based frontend. Older but mature for the bidirectional NL↔formal mapping pattern. Search github for "nl2spec" if you want a working baseline for that specific affordance. arxiv

My practical recommendation for build order:

Start with Apalache + Specula — these are real, working, documented. Specula gives you brownfield spec extraction; Apalache gives you the symbolic check. Together they cover roughly half your pipeline with maintained code.
Build your translator inspired by Req2LTL's two-stage architecture — clone their repo to see the actual prompts and the OnionL grammar, but plan to fork or reimplement against your own intermediate representation that fits your domain (smart contracts? DeFi protocols? procurement?). The pattern is the contribution; the specific OnionL grammar is aerospace-flavored.
Use the ALICE paper as your contradiction taxonomy reference. Re-implement the seven-question decision tree against your translated formal output. The seven questions are the part you copy; the GPT-3 specifics are obsolete.
Use VERIFYAI as a reference architecture for the overall pipeline shape, not a tool to install.
The closure-as-action-gate part is what nobody else has built. That's your wedge.

For consumable writing to read before any coding: the Specula SIGOPS blog post, the Brooks structural-backpressure post we started with, and the Req2LTL paper (the OnionL section specifically) are the three I'd read in that order. Together they give you the methodology, the philosophy, and the translation architecture in about three hours of reading.You said: i need to create somthing language agnostic - wdyti need to create somthing language agnostic - wdytMay 25Claude responded: Strong instinct, and the right one.Strong instinct, and the right one. But "language agnostic" has at least three orthogonal meanings, and they imply very different architecture decisions. Let me disambiguate, then sketch what the architecture looks like if you want all three.
The three axes:

Programming language agnostic — works whether legacy code is Solidity, Go, Rust, TypeScript, Python, Java
Formal language agnostic — doesn't lock into TLA+; can target Alloy, Lean, Z, Dafny, LTL, FOL, whatever fits the verification task
Natural language agnostic — Portuguese, English, Spanish input all flow through the same pipeline

These are independent. You can be one without the others. My read of your instinct is you want at least #1 and #2; #3 falls out almost for free once the other two are right.
The architectural implication: the IR becomes the backbone
In a single-language, single-formalism tool, you can let the formalism dominate the architecture (Req2LTL is a Linear Temporal Logic tool; everything is shaped by LTL's semantics). In an agnostic tool, the formalism is a backend, not the spine. The spine is your intermediate representation — the format every requirement gets translated into before any specific verification system touches it.
This IR is the single most consequential design decision you'll make. Get it right and adapters slot in cleanly; get it wrong and you'll be patching mismatches forever. Most tools that tried to be formalism-agnostic failed at this step — they ended up with an IR that secretly favored one backend, or an IR so abstract it couldn't express what real requirements need.
What the IR has to be able to express:

Entities (the nouns of the system: users, accounts, transactions, deposits)
State variables with types and value domains
Actions/transitions with pre- and post-conditions
Invariants (predicates that must hold in every state)
Temporal properties (always, eventually, leads-to, until)
Quantifiers (for-all, exists, with scope)
Numeric and logical constraints
References to external context (database queries, oracle reads, on-chain state)
Provenance (which NL fragment this came from — for the bidirectional mapping nl2spec uses)
Confidence/uncertainty markers (which premises were LLM-discharged vs deterministic)

Most existing work picks a subset of this. OnionL covers temporal + propositional + scope. ALICE's controlled NL covers conditionals + atomic statements. JSON-LD in VERIFYAI is more general but underspecified semantically. None of them cover all of it well, which is partly why each tool targets a narrow domain.
A good IR for your purposes probably needs:

A core typed lambda calculus or sequent-shaped notation (the spine)
Extension points for backend-specific annotations (a Dafny annotation, a TLA+ annotation, an Alloy annotation — each backend reads its own)
Explicit support for partial specifications (a requirement might fully discharge for one backend and only partially for another)

The novel angle this unlocks
Here's the part that's genuinely new and that I haven't seen anyone do: multi-backend closure. Different premises in the same requirement can be discharged by different verification systems, and the closure gate only opens when all premises — across all backends — are closed.
Concrete example. A requirement against tBTC: "a redemption must complete within 6 hours of approval, must transfer the correct BTC amount, and must invalidate the deposit record."
Premises:

Temporal: completion within 6 hours → LTL backend or TLA+ with clock variables
Numeric correctness: BTC amount math → SMT solver directly (Z3 or CVC5)
State transition: deposit record invalidation → TLA+ or Alloy
Authorization chain: only authorized redeemer can trigger → first-order logic or sequent rules (Shen-style)

Today, you'd either (a) pick the most powerful formalism that can express all of this and pay the verification cost across the board, or (b) split the requirement manually across tools and lose unified closure. With an agnostic IR + multi-backend dispatcher, each premise routes to the cheapest backend that can discharge it, and the proof object aggregates the results.
The proof object becomes: {P1: discharged by Apalache trace X, P2: discharged by Z3 proof Y, P3: discharged by Alloy instance Z, P4: discharged by sequent calc rule R}. The action gate opens only when every entry is closed. Auditable, mechanical, and the choice of backend per premise is itself a recorded decision.
This is the structural-backpressure thesis pushed to its natural conclusion: the closure gate doesn't care which verifier closed which premise, only that they all closed.
The honest tradeoff
Agnosticism costs you v1 simplicity. A truly agnostic system needs:

A well-designed IR (this is where most projects sink)
N programming-language adapters (impact analysis, trace extraction, code-to-spec mapping per language)
M formal-backend adapters (translator from IR to TLA+, Alloy, Lean, etc.)
A dispatcher that picks the right backend per premise
Cross-backend consistency checking (do the Alloy and TLA+ projections of the same IR agree?)

That's a lot of surface area for a v1. The standard advice would be "pick one + one, ship, iterate." But the counter-argument matters here: retrofitting agnosticism is harder than starting with it. If the IR isn't there from day one, every backend you add will have a slightly different mental model of what a requirement is, and you'll spend years reconciling them. Look at LSP (Language Server Protocol) for a successful version of this story — Microsoft designed the protocol first, then everything else followed.
Recommended path
Design fully agnostic. Ship one concrete pair to validate the IR. Then expand.
Concretely:

Spend real time on the IR. Treat it as the contribution. Get feedback from people working in multiple formalisms (TLA+ folks, Alloy folks, Lean folks) before you commit. The IR is the standard you're trying to set.
V1 ships with one programming-language adapter and one formal-backend adapter — for you, almost certainly Solidity + Apalache (your home turf, biggest immediate value). But the IR is fully expressive; the adapters are just two of many possible.
V1.5 adds a second backend (probably Z3 or CVC5 for pure SMT premises that don't need a full model checker). This is the first real test of whether the IR works — can you route premises across backends and still close the proof?
V2 adds a second language (probably Go, since Specula is already there and tBTC has off-chain Go components). Tests whether the language-adapter abstraction holds.
Multilingual NL falls out free once the translator targets the IR rather than a specific formalism — modern LLMs handle Portuguese, Spanish, English, etc. equivalently if the output schema is consistent. You'd add Portuguese support as a prompt-engineering exercise, not an architecture change.

What this positions you as
A single-language, single-formalism tool is a research artifact. A genuinely agnostic IR + dispatcher + closure-gate system is infrastructure. It's the difference between "another tool in the formal methods space" and "the requirements layer everything else plugs into."
The Wanabai / Attestation Layer framing from your earlier papers fits this exactly. The attestation layer was about making model outputs verifiable through a substrate-agnostic surface. This is the same move for the input side: making requirements verifiable through a substrate-agnostic surface. Both reach for the same shape — a universal verification protocol that doesn't care about the specific implementation of either the producer (model, human) or the verifier (TLA+, Alloy, Z3, Lean).
Done right, the IR is the artifact that outlives the tool. Even if your specific implementation gets superseded, an IR that turns out to be the right shape becomes a standard that other tools target. That's a different kind of contribution than "we built a better requirements validator."
One concrete starting question to anchor the IR design: can you express the safety property of tBTC's bridge redemption in your IR, then have it project cleanly into both a TLA+ spec for Apalache and an Alloy model for the structural part? If yes, the IR is on the right track. If you find yourself adding TLA+-specific or Alloy-specific escape hatches to make the projection work, the IR isn't general enough yet.You said: im meaning Programming language agnostic — works whether legacy code is Solidity, Go, Rust, TypeScript, Python, Javaim meaning Programming language agnostic — works whether legacy code is Solidity, Go, Rust, TypeScript, Python, JavaMay 25Claude responded: Clearer scope, good.Clearer scope, good. That's actually the easier of the three to get right, and the architecture pattern is well-established: a language adapter layer with a small, well-defined interface, and one adapter per language.
The adapter interface
Every language adapter needs to provide a small fixed set of capabilities. Get this interface right and adding new languages becomes plumbing rather than redesign:
LanguageAdapter:
  # Impact analysis
  resolveSymbols(requirement_terms) → Symbol[]
  callGraph(symbol) → CallGraph
  affectedModules(symbols) → Module[]

  # Code presentation for spec extraction (Specula-style)
  presentToLLM(module) → canonical text + metadata

  # Trace extraction
  extractTraces(module, execution_data) → NormalizedTrace[]

  # Coverage manifest parsing
  parseManifest(path) → { spec_module → code_modules[] }
That's roughly it. Everything else in your pipeline (the IR for requirements, the formal backend, the closure gate, the proof object) is language-independent and doesn't care which adapter produced the inputs.
Tool inventory per language (so you know what already exists)
You don't have to build the static analysis or tracing from scratch. Each language has mature tooling; the adapter is mostly a thin wrapper:
LanguageStatic analysis / call graphTrace extractionSoliditySlither (Python), Slang (Rust, NomicFoundation), solidity-lspFoundry traces, debug_traceTransaction on Geth/Reth, TenderlyGogopls, go/analysis, golang.org/x/tools/go/callgraphruntime/trace, OpenTelemetry, eBPFRustrust-analyzer, syn crate, MIR via rustc internalstracing crate, OpenTelemetry, tokio-consoleTypeScripttsserver, ts-morph for AST manipulationasync_hooks, OpenTelemetry, Chrome DevTools ProtocolPythonpyright, jedi, built-in ast modulesys.settrace, OpenTelemetry, py-spyJavaEclipse JDT, ASM, SpotBugsJFR (Java Flight Recorder), OpenTelemetry, async-profiler
The pattern: for static analysis, Language Server Protocol gives you 80% of what you need across all of these — it's literally designed as a language-agnostic interface for editor tooling, and it exposes exactly the symbol-resolution and call-graph capabilities you need. Most adapters can start as an LSP client plus a small bit of language-specific post-processing.
The actually hard piece: trace normalization
Static analysis abstracts cleanly across languages. Trace extraction does not. The semantic models are genuinely different:

EVM languages (Solidity, Vyper) produce transaction traces — sequences of opcode executions with full state diffs, deterministic, on-chain. Every state transition is observable.
Native code (Go, Rust, Java) produces runtime traces — call stacks, goroutine/thread interleavings, memory allocations. Non-deterministic across runs, often partial.
JS/TS produces async traces with promise chains and event loop ticks. Different shape again.
Python has very rich introspection but the GIL plus dynamic typing makes trace semantics fuzzy.

You need a NormalizedTrace schema that all of these can project into. OpenTelemetry's span model is the closest thing to an industry standard for this (cross-language, designed for distributed systems), and I'd start there even though it wasn't designed for formal verification specifically. Something like:
NormalizedTrace = sequence of TraceEvent
TraceEvent = {
  timestamp,
  actor,              # contract address, goroutine ID, thread name
  action,             # function called, opcode, event emitted
  pre_state_diff,     # what changed before the action
  post_state_diff,    # what changed after
  causal_predecessor, # which event caused this one
  metadata            # language-specific extras
}
This is the part where the actual research happens. The normalization decisions are load-bearing — too narrow and you can't represent some language's semantics; too wide and the trace validation step can't reason about it.
The wedge this unlocks: cross-language requirements
Here's the move that single-language tools cannot make and that justifies the agnostic architecture: a requirement that spans multiple languages can be validated as a single proof.
Take tBTC as the canonical example. A real requirement looks like:

"When governance approves a parameter change via on-chain vote, the off-chain coordinator must apply the change within the next epoch, the operator clients must acknowledge it within 5 minutes of broadcast, and the frontend must reflect the new value within the next user session."

That requirement touches:

Solidity — the governance contract
Go — the coordinator service
Go or Rust — the operator client
TypeScript — the frontend

No existing tool can validate this end-to-end. Certora can prove the Solidity part. Apalache could spec the coordinator state machine. Frontend behavior is essentially unverified. The cross-language causal chain — "this on-chain event → this off-chain action → this client behavior → this UI state" — is exactly what nobody is doing systematically.
Your tool, with adapters for each language and a unified trace normalization, can. The requirement gets translated into your IR once, premises get routed to the appropriate analyzer per language, traces get extracted from each subsystem and stitched into a cross-language trace, and the closure gate checks whether the combined evidence discharges the requirement.
This is the wedge. Single-language tools commoditize at the language level — Slither for Solidity, gopls for Go, etc. A multi-language requirements validator sits at a layer where there is no current competition because nobody has built the trace-normalization plumbing yet.
V1 recommendation, given your situation
Your obvious move is Solidity + Go as the v1 pair, because:

You have direct domain expertise in both through tBTC — you know what the requirements look like, you know the failure modes, you can write meaningful invariants.
tBTC itself is the perfect demo system — multi-language, security-critical, with real auditable requirements (the TIPs you've been working with).
Specula already covers Go-side spec extraction — you don't need to build that piece.
Solidity-side spec extraction is underserved — there's no equivalent of Specula for Solidity. Building it would itself be a contribution. (Slither + LLM + trace validation from debug_traceTransaction would be the pattern.)
The cross-language demo writes itself — "here is a TIP-shaped requirement that spans the on-chain contracts and the off-chain coordinator; here is the unified proof that it closes."

V2 adds TypeScript (frontends) and maybe Rust (operator clients in some Bitcoin tooling). By the time you've shipped V1, the adapter interface will have been pressure-tested by two very different languages (EVM bytecode vs Go runtime), so adding a third should be straightforward.
One concrete IR design question to test this
The interface design works iff this requirement can be expressed in your IR without language-specific escape hatches:
"A redemption is valid iff the on-chain contract Bridge has emitted RedemptionRequested with parameters (P), AND the off-chain coordinator's state contains a matching pending_redemption(P) within 30 seconds, AND the operator quorum has signed the corresponding Bitcoin transaction within the SLA window."
If your IR can express that requirement cleanly, with the language-specific parts hidden inside the adapter symbol-resolution step, you're on the right track. If you find yourself needing distinct solidity::Event and go::ChannelMessage types in the IR itself, the language boundary has leaked into the spine and the design needs another pass. The IR should describe what needs to be true; adapters describe how to check it in each language.You said: in one paragraph, very simple terms and graounded, what is the system im trying to buildin one paragraph, very simple terms and graounded, what is the system im trying to buildMay 25Claude responded: You're building a gatekeeper for natural-language requirements: a system that takes a human-written requirement (like "users can only refund their own orders")…You're building a gatekeeper for natural-language requirements: a system that takes a human-written requirement (like "users can only refund their own orders"), translates it into formal logic, then automatically checks three things — is the requirement self-consistent, is it consistent with the existing system's verified behavior, and is it actually implementable given the current code — and only lets it through to the engineering backlog if all three checks pass; if any check fails, it returns a precise explanation of what's missing, contradictory, or in conflict, instead of a vague "needs clarification." It works across programming languages (Solidity, Go, Rust, TypeScript, etc.) so requirements that span a full stack can be validated as a single proof, and it borrows existing tools (Specula for extracting specs from code, Apalache for the formal check, Req2LTL-style translation from English to logic) to do most of the heavy lifting — your contribution is the integration and the rule that nothing ships until the proof closes.You said: good, generate a VERY COMPREHENSIVE plan for building the NL attestation layergood, generate a VERY COMPREHENSIVE plan for building the NL attestation layerMay 25Claude responded: Plan is in the file.Created a file, read a fileCreated a file, read a filePlan is in the file. Fifteen sections, ~6,500 words. A few structural notes on what I tried to do:
Foregrounded the IR design as the most consequential decision in Section 3 with a concrete syntactic sketch for a tBTC-style requirement. The IR is the thing that, if you get it right, makes everything else slot in; if you get it wrong, you'll be patching for years. Worth spending Phase 0 entirely on getting that right.
Phased the build conservatively. Phase 0 (3 months) is just IR + validator + toy demo. Phase 1 (6 months) ships Solidity end-to-end. Phase 2 (6 months) is the cross-language wedge. Phase 3 (9 months) is hardening. The aggressive option would be to ship Solidity in 3 months, but the IR is the artifact you'll regret rushing — better to spend the time up front and have a foundation that supports the next decade.
Tied naming to the existing Attestation Layer paper explicitly. The continuity is real and worth being deliberate about: output attestation makes artifacts verifiable, input attestation makes requests verifiable. Together they bracket the agentic system. The framing positions this as Paper 6 in your series.
Was honest about open research questions in Section 12. The 88% / 99% accuracy numbers from Req2LTL and ALICE were measured on cooperative authors writing cleanly; real production teams write messy requirements. Translation robustness under adversarial inputs is genuinely uncertain and should be measured early.
Marked the cross-language angle as the wedge. Single-language requirement validators have to compete with mature single-language tools (Certora for Solidity, etc.). A multi-language requirement validator sits at a layer where nobody currently builds because nobody has the trace-normalization plumbing. That's the genuinely defensible position.
A few things I deliberately left for later detailed design work, since they need more thought than fits a build plan:
The exact IR syntax and grammar — Section 3 has a sketch but a real spec needs formal grammar, type system rules, and a reference parser. That's a deliverable of Phase 0, not the build plan.
The DSL for input requirements — Section 4.1 describes the constraints, but the actual grammar needs to be designed against real requirement corpora. Sample requirements from tBTC governance proposals would be the right starting corpus.
The trace normalization schema — Section 6.4 has a sketch but the real schema will evolve substantially during Phase 1 when the first adapter forces hard semantic choices. Better to leave it deliberately under-specified now than to over-commit.
The threat model and security analysis — Section 13 names the risks but a real security review is its own document, particularly given that this system gates production code changes.
If you want, the natural next artifacts from here are: (1) the IR specification document as a standalone formal spec, (2) the Phase 0 deliverable plan with weekly milestones, or (3) the paper draft for the IR spec announcement. Each of those is the focused next step from this overview.You said: updated the plan, vetupdated the plan, vetMay 25Claude responded: This is a substantially stronger document than the original.Viewed 2 filesViewed 2 filesThis is a substantially stronger document than the original. The honest framing about evidence levels is the single biggest improvement, and the rest follows from that recalibration. Let me walk through what's now right, what I'd still push back on, and a few strategic questions you should make conscious decisions about rather than letting them get answered by default.
What you fixed that the original got wrong
The evidence-level taxonomy (§2.3) is the load-bearing improvement. The original conflated "model checking found no violation within bound k" with "proved." That conflation is exactly what gives formal methods a bad name in practice — people sell bounded results as proofs, the system ships, an unbounded counterexample shows up in production, and the team loses faith in the whole approach. Distinguishing PROVEN_INDUCTIVE, BOUNDED_CHECKED(k), SMT_CHECKED, TRACE_VALIDATED, and TYPE_CHECKED as separate first-class statuses is intellectually correct and will save you from overpromising. Keep this taxonomy front and center; it's the single most defensible part of the design.
Reframing the output from "closed proof object" to "implementation-ready spec package" (§10) is right. Engineers and agents can build from a spec package. They can't build from a proof object — they have to interpret what it means. The package framing also matches what teams actually want: a deterministic target that survives the human-to-engineering handoff. The original's closure-gate semantics promised more than the system can deliver; the package framing promises exactly what it can.
Dropping the cross-language ambition from v1 is correct. I pushed cross-language as "the wedge" in our conversation, but you're right to scope it out. Until the single-language vertical actually closes against a real tBTC requirement, multi-language is fantasy. The decision to defer it past Phase 4 is the right call. (See strategic question below about whether to mention it at all.)
The concrete first milestone (§18) is excellent. A specific directory layout and a CLI invocation that should work — nlreq validate requirements/TBTC-REQ-RED-AUTH-001 — is far more actionable than the original's abstract phase deliverables. This is what a Phase 0 engineer would actually use to know they're done.
The shadow → soft gate → hard gate adoption path (§12) is the right sequencing. A gate that immediately blocks PRs never gets adopted. Starting in report-only mode lets the team build trust in the signal before any developer is blocked by it. Worth being explicit that "trust" is measured by false-positive rate, not by absence of complaints.
Restricting the v1 grammar to six claim kinds and one rule pattern (§5.2, §6.1) is appropriately narrow. The original tried to be expressive; the rewrite is the inverse and that's correct. Add complexity only when a real requirement forces it.
What I'd still push back on
Layer 5 / Layer 6 boundary is fuzzy. The architecture diagram has "Evidence Aggregator" at Layer 5 and "Handoff and Gate" at Layer 6, but Layer 6 is doing two things: (a) deciding the final status from the aggregated evidence and (b) emitting the package and gate output. Those are distinct responsibilities. Consider splitting: Layer 6 = "Status Decision" (pure function: evidence + required levels → final status), Layer 7 = "Package and Gate Emission" (effects: write files, post CI comments). This matters because Layer 6 is testable in isolation if it's pure; mixed with effects it becomes integration-tested only.
The LLM-drafted controlled-language path (§6.3) is underspecified and is the biggest hidden risk. You correctly restrict LLMs from being proof authorities. But you allow them to "suggest a controlled-language rewrite" from free-form input. That LLM rewrite is making semantic decisions about how to interpret ambiguous prose. If the user accepts the rewrite without scrutiny, the LLM's interpretation becomes the requirement — and the downstream verification then proves something other than what the user meant. Two specific fixes:

The LLM-suggested controlled form must be presented to the user with a side-by-side diff against the original free-form input, and the user must explicitly approve before the parser runs.
The implementation spec package should preserve both the original free-form text and the controlled form, with the diff between them recorded as part of the audit trail. If the controlled form was LLM-rewritten, that fact and the diff are first-class evidence the package consumer sees.

NEEDS_REVIEW workflow is named but not specified. Section 4.3 says LLM-generated IR is marked NEEDS_REVIEW until reviewed. But the document does not specify: who reviews, what they're checking, what the artifact of review looks like, or how the status transitions out of NEEDS_REVIEW. Without this, in practice the status will become a junk drawer where things accumulate. Recommend: a short review checklist (binding correctness, claim shape matches intent, assumptions explicit) committed as part of the package, signed by a named reviewer, before the status can change.
Refused requirement iteration loop is missing. Statuses include REFUSED_AMBIGUOUS, REFUSED_UNBOUND_SYMBOLS, etc. — but the document does not describe how a user iterates. Do they get a structured explanation of why it was refused, mapped back to which fragment of their input? If not, the refusal is functionally equivalent to "broken, try again," which is the failure mode of every formal-methods tool that didn't survive contact with users. The original had bidirectional NL ↔ IR provenance for exactly this reason; the rewrite dropped it. Recommend adding back: every claim in the IR carries a source_span referencing character positions in the controlled NL input, so refusals can be presented with the specific phrase highlighted.
Self-consistency checking is implicit, not explicit. The original called this out as an ALICE-style backend. The rewrite folds it into "SMT for contradiction checks over simple formulas" (§8.1). This is a real demotion. A requirement of the form "for every X, if A then B; for every X, if C then not B" with overlapping A and C is internally inconsistent regardless of the system. The system should detect that before any system-consistency check runs. Recommend either making this a named backend or adding an IR-validation rule that runs SMT on the conjunction of all claims' conditions to flag internal contradictions before dispatch.
IR versioning needs a migration story. Section 5.3 starts with ir_version: 0.1, which is good practice. But there's no description of what happens when the IR schema changes and existing requirement packages reference old versions. Migration scripts? Auto-upgrade with validation? Hard-fork? This will hurt within 12 months if not addressed. Recommend at least a placeholder in §5 stating the policy.
Phase 0 success criterion is too easy. "One controlled requirement becomes a validated IR, one SMT query runs, and one implementation spec package is emitted." This is achievable in a weekend if you cut corners. Suggest tightening: "Three controlled requirements representing the three most common claim kinds (authorization precondition, state postcondition, numeric invariant) each produce validated IR, executed SMT queries, and complete spec packages, with golden test files that can be diffed across runs to prove determinism." This forces actual coverage of the grammar surface, not just one path.
Smaller items
The example IR (§5.3) uses forall with type RedemptionRequestInput, but the claim schema isn't formally defined elsewhere. Recommend an appendix with the IR JSON Schema in full — the inline example is illustrative but the actual schema is the contract. A consumer of v0.1 should be able to generate a parser from the schema.
Section 8.2's evidence object recording "bounds, constants, model scope, checker version, and command line" is exactly right and worth highlighting more prominently. Reproducibility of formal results is the differentiator from "we ran some tool once" — make sure this discipline carries into Phase 2 deliverables explicitly.
The recommended first target (§17) lists four good candidates but doesn't pick one. Pick. "Unauthorized callback redemption must revert" is the strongest because the failure mode is concrete, the test surface is small, and the property is structural rather than economic. Naming the specific target in the document closes a decision that will otherwise drift.
Tooling map (§14) doesn't pick within "Lark or ANTLR," "Z3 or CVC5," "Apalache or TLC," "JSON Schema, Pydantic, or Zod." Each "or" is a deferred decision. Phase 0 should pick one of each and commit. Recommend: Lark (Python ecosystem fit), Z3 (most mature), Apalache (better counterexamples than TLC), Pydantic (best Python schema validation). Document the rationale for each choice in an ADR.
Strategic questions for you to make conscious
Question 1: Is the cross-language wedge gone, or just deferred? The original positioned multi-language requirement validation as the genuinely-novel contribution that defends against single-language competitors (Certora for Solidity, etc.). The rewrite drops this framing entirely. Two valid paths:

Deferred but explicit: Add a §20 "Strategic Roadmap Beyond v1" that names cross-language as the long-term differentiator, so investors/collaborators/your future self know it's not abandoned.
Permanently scoped out: Accept that the product is "best-in-class Solidity requirement validator" and compete on that ground.

Both are reasonable. Make the decision explicit rather than letting Phase 4's mention of "limited Go adapter for one off-chain component" be the silent answer.
Question 2: Is the connection to the Attestation Layer / Wanabai paper series intentional or coincidental? The rewrite drops the framing tie. If this is meant to stand as its own intellectual project, fine. If it's meant to be Paper 6 in the series, the introduction should say so. Tying it into the existing framework gives readers context and gives you publication economy.
Question 3: What's the realistic team size? 26 weeks of phased deliverables implies sustained engineering effort. If this is you solo as a side project alongside tBTC work, the timeline is unrealistic. If it's funded with one or two engineers, it's feasible. The plan should at least name a baseline staffing assumption so phase estimates are anchored to something.
Overall
The recalibration from "structural backpressure forces correctness" to "explicit evidence levels prevent overpromising" is the right intellectual move and was the thing the original plan most needed to fix. With the LLM-drafted-controlled-form risk addressed, the refused-requirement iteration loop specified, and the architecture's Layer 5/6 split tightened, this plan is buildable as written. The Phase 0 milestone in particular is the kind of crisp, achievable target that distinguishes plans that ship from plans that get rewritten forever.
If you want to take one immediate action: pick the four "or" choices in §14, write a single-page ADR for each, and commit them. That alone moves Phase 0 from "ready to plan" to "ready to start."You said: updatedupdatedMay 25Claude responded: Strong revision.Viewed 3 filesViewed 3 filesStrong revision. You systematically addressed nearly every substantive item from the previous vet, and the plan is now at a state where the next move is starting Phase 0, not iterating further on the document. Let me confirm what's now fixed, flag the few small things that remain, and name the concrete first actions.
What you addressed correctly
The architecture split into Layer 6 (pure status decision) and Layer 7 (effects) is exactly what was needed, and §3 now explicitly states Layer 6 stays pure and unit-testable. §4.8 formalizes it as a pure function with declared inputs and outputs and notes that golden tests verify determinism. This is the right shape.
The LLM-rewrite hazard is now fully bounded. §4.3 requires the package to preserve original text, LLM suggestion, approved form, diff, model metadata, prompt version, timestamp, and explicit approval, and §6.3 requires side-by-side approval before any parser runs on a rewrite. No silent semantic shifts can slip through this design.
The NEEDS_REVIEW workflow (§5.6) is no longer a junk drawer. The required review.yaml, the seven-item checklist, and the hash-binding to specific artifact versions give it a real exit path. The example payload is concrete enough that Phase 0 can build against it.
The refusal iteration loop (§9.4) is the right shape. Every refusal carrying next_actions plus a source_span pointing to the failing fragment converts "broken, try again" into "fix this specific phrase or add this specific binding." This is the difference between a tool people adopt and a tool people abandon.
Self-consistency is now a first-class backend (§8.1) with its own evidence level (CONSISTENCY_CHECKED), and the v1 scope is correctly limited to "what SMT over IR can express" rather than overpromising full ALICE coverage. The CLI output in §18 shows the consistency line, which makes the user-facing evidence trail complete.
IR versioning (§5.2) with the no-silent-upgrade rule, the migration command preserving prior IR hash and migration diff, and CI rejection of unsupported ir_version is exactly the policy needed. This will save real pain in month 12.
Phase 0 success criterion is now serious — three claim kinds, byte-stable golden outputs, fully exercised pipeline. This is appropriately hard to fake. The phased tooling commitments (§14.1) with Python/Lark/Pydantic/Z3 plus the ADR requirement and the "future options" deferred to §14.2 closes all the "or" decisions cleanly.
The team-size disclaimer in §13 (one focused full-time engineer; 2-3x for solo side-project) and the strategic roadmap in §20 (cross-language deferred, not abandoned) are both honest and consciously stated rather than left ambiguous.
Small items still worth a pass
Reviewer identity in solo mode. §5.6 requires "reviewer identity" but doesn't address the solo case where the author is the only available reviewer. For tBTC-internal use this is fine because Piotr, Maclane, or Lev can play the reviewer role. For solo side-project mode, consider adding: "If author and reviewer are the same person, the review must be performed at least 24 hours after the controlled-form approval, with the checklist treated as a self-audit. The package records this fact." It sounds bureaucratic but it's the only way to prevent the review degenerating into rubber-stamping in solo work.
Phase 0 covers 3 of 6 claim kinds. §13 Phase 0 success criterion specifies authorization precondition, state postcondition, and numeric invariant. The other three v1 claim kinds (state precondition, event/state correspondence, bounded temporal) appear in Phase 1+ work. Worth one sentence in §13 explaining: "These three kinds are chosen for Phase 0 because they exercise the full pipeline shape without requiring trace integration or temporal reasoning, which arrive in Phase 1 and Phase 2." Otherwise readers will wonder why the others were excluded.
Source span stability. §5.1 introduces source_span with start_char/end_char. If the controlled text is reformatted (whitespace, trailing newlines), positions shift and existing IR documents become inconsistent. Add a one-liner: "Source spans refer to the canonical controlled form after normalization (single newline between lines, trimmed leading/trailing whitespace, two-space indent). The normalization rule is part of the parser and is versioned with ir_version." This is small but matters once the system has any history.
CLI refusal example missing. §18 shows the ACCEPTED_WITH_EVIDENCE output. Adding a second block showing a REFUSED case — with the source_span, the next_actions, and the offending fragment quoted — would make the user-facing experience as concrete as the success case. Right now the doc is asymmetric: clear on what success looks like, vaguer on what failure looks like.
Auxiliary file schemas. The directory listing in §18 includes assumptions.yaml, verification-tasks.yaml, and review.yaml. The IR YAML and bindings YAML and evidence YAML have inline examples, but these three don't. Not a Phase 0 blocker, but they'll need schema definitions before Phase 1 starts since they're consumed by the binder and the dispatcher. Worth listing them explicitly as Phase 0 schema deliverables alongside the IR JSON Schema.
Architecture diagram direction. §3's layered diagram is read bottom-up but the data flow in §4 is also bottom-up. Consider adding the data-flow arrow (↑) between layers in the diagram itself, just to make the reading direction immediately visual. Cosmetic but useful for newcomers.
None of these are architecture problems. They're documentation polish, and the right time to fix them is when you write the implementation rather than now.
What I'd remove from the iteration cycle
You're done iterating on this plan. Further revisions will be diminishing returns on a document that already covers everything a Phase 0 engineer needs. The plan should now be frozen as v0.1, committed to a repo with its own ADR-style versioning, and used as the implementation reference. Future changes happen as PRs against the plan based on what you learn from building, not from re-reading.
Concrete next actions
In order, what an honest Phase 0 kickoff looks like:

Create the repository. A monorepo under whatever name you choose (nlreq is the CLI you used in §18 — that's probably the project name too). Commit this plan as docs/build-plan.md at v0.1.
Write the four ADRs. docs/adr/0001-phase-0-tooling.md (Python/Lark/Pydantic/Z3), 0002-ir-versioning-policy.md (the §5.2 policy as standalone reference), 0003-llm-rewrite-approval-protocol.md (the §4.3 + §6.3 requirements as standalone reference), 0004-status-decision-purity.md (the §3 + §4.8 contract for Layer 6). Each ADR is one page. They become the contracts the implementation must satisfy.
Write the IR JSON Schema. This is the single highest-leverage Phase 0 artifact. Everything else depends on it. Pydantic models + model_json_schema() is the fastest path; commit both the Python sources and the generated .schema.json. Validate the three example IR fragments against it as the first golden tests.
Write the Lark grammar for the §6.1 rule pattern. One file, maybe 50-100 lines. Includes the seven expected_result variants and the supported conditions. Add a CLI command nlreq parse <file> that emits the AST as JSON.
Implement Layer 6 as a pure function and unit test it. Status decision based on evidence input. Eight to ten golden test fixtures covering the status matrix (each refusal mode, each acceptance mode). This is the easiest layer to write and the one whose correctness is most load-bearing for the rest of the system.

The first four are roughly a week of focused work. The fifth is another week. After that you have parser + IR + status decider, and the SMT integration becomes the question of plumbing rather than design.
The plan is good. Time to build it.You said: why slither and forge are mentioned in the plan?why slither and forge are mentioned in the plan?May 25Claude responded: They serve orthogonal purposes — one reads code, the other watches code run — and the plan needs both because the system has both kinds of needs.They serve orthogonal purposes — one reads code, the other watches code run — and the plan needs both because the system has both kinds of needs.
Slither's role: static analysis for symbol binding. When a controlled requirement says request_redemption, the system needs to map that to a specific Solidity symbol — Redemption.requestRedemption(...) — and verify the mapping is unambiguous across the contract's inheritance hierarchy. Slither does this kind of inheritance-aware symbol resolution, call-graph construction, and modifier propagation better than solc alone. solc's --ast-json gives you the parse tree of a single file; Slither gives you the project-level view that's needed when a binding crosses contracts, libraries, or virtual function overrides.
What Slither specifically buys you in §7:

Verifies that the symbol named in bindings.yaml actually exists at the resolved location
Detects overloaded functions with the same name (which trigger REFUSED_UNBOUND_SYMBOLS under §9.3)
Provides the call-graph data needed for §7.3's binding-failure checks ("the target function is overloaded and unresolved")
Gives the slither_analysis confidence tag in §7.2

Foundry's role: trace generation for the trace validation backend. When the system claims TRACE_VALIDATED evidence (§8.4), something has to actually run the unauthorized-callback scenario and capture what happened. Foundry produces structured, scriptable execution traces — function call paths, revert/success outcomes, emitted events, decoded parameters — that the trace validator can compare against the expected behavior in the IR. The forge test runner plus the trace JSON output is the simplest path to this.
What Foundry specifically buys you:

Deterministic test execution against the contract under verification
Trace output that's machine-readable (the alternative is parsing Hardhat's less structured logs)
Fast iteration — Foundry tests run in seconds, which matters when the package is generated as part of CI
The traces/C2.json file in the §18 directory listing comes directly from this

Why both and not one or the other. Slither cannot tell you whether the unauthorized callback actually reverts at runtime; it can only verify that the function exists and what its modifiers say. Foundry cannot tell you whether the symbol you bound in bindings.yaml is the right one across an inheritance graph; it just runs whatever you call. The two cover non-overlapping concerns: static binding integrity (Slither) versus dynamic behavior conformance (Foundry).
When they enter. Neither is needed in Phase 0 — Phase 0 uses a "static symbol-binding stub" and has no trace validation. Both arrive in Phase 1 ("Solidity binder using build artifacts and Slither" + "Foundry test/trace integration"). The mentions in §2.1 and §14.3 reflect the overall v1 scope, not Phase 0 specifically. If you wanted to be more precise, §14.3 could be split into "Phase 1 Solidity tools" (solc + Slither + Foundry) vs Phase 0's minimal stack (just solc AST is enough).
Could either be substituted?

Replacing Slither with solc + handwritten resolution: feasible for Phase 1's single-contract scope but starts hurting once requirements touch contracts that inherit or use libraries. Defensible only if you commit to bindings always being explicit and never ambiguous, which the plan doesn't.
Replacing Foundry with Hardhat: doable but the trace surface is worse. Hardhat's traces require more glue code to extract structured data. If tBTC's existing test suite is Hardhat-based, you'd still want a thin Foundry sub-suite specifically for trace-validation purposes, because the trace output is what the verifier consumes.

The honest minimal version. If you wanted Phase 1 with strictly the smallest tool set: solc AST + Foundry. Skip Slither, accept that bindings must be unambiguous and manually specified, and add Slither only when an ambiguous-binding scenario actually fails. That's a defensible cut and would shave a couple of days off Phase 1. The plan as written includes Slither earlier because tBTC's contracts have non-trivial inheritance (Bridge/Wallet/Bank pattern) and ambiguous bindings will appear immediately on the first non-toy requirement.You said: but arent these for solidity?but arent these for solidity? im creating a agnostic attestaion layer - not solidity attestation layerMay 25Claude responded: You're right and I should have pushed back on this in the previous vet rather than waving it through.You're right and I should have pushed back on this in the previous vet rather than waving it through. The plan drifted from "agnostic architecture with Solidity as first adapter" to "Solidity validator with cross-language as future work." Those are two different products, and you wanted the first one.
The distinction matters for positioning, not just scope:

Solidity attestation layer competes with Certora, Halmos, SMTChecker, Slither itself. Mature, opinionated competitors. The wedge is narrow.
Agnostic attestation layer, Solidity as the first adapter sits at a layer where there is no competition because nobody has built the adapter abstraction. The wedge is the architecture, not any specific language coverage.

Same v1 deliverables, fundamentally different product. The current plan's text sells the first one even though the title says the second one.
Where the plan drifted Solidity-specific (sections that need restructuring, not rewriting):
§7 "Symbol Binding" is titled "Solidity V1" and the whole section is Solidity-specific tooling (Slither, solc AST, ABI). This should be split: §7 specifies the adapter interface — what every adapter must provide — and §7.1+ shows Solidity as the first implementation of that interface.
§8 "Verification Backends" mixes agnostic backends (Z3, Apalache, generic trace validation) with Solidity-specific tooling (Foundry, Geth/Reth traces). The backends themselves are language-neutral; the adapter's job is to translate IR claims into language-neutral queries the backends can consume. This split needs to be explicit.
§14 "Tooling Map" has §14.3 titled "Solidity" but doesn't separate the agnostic core (Z3, TLA+, IR schema tools, parser generators) from the Solidity adapter's specific tools. Should be: §14.A "Core (agnostic)," §14.B "Solidity adapter," with the implication that future adapters get their own §14.C etc.
§13 Phase 0 deliverables include "static symbol-binding stub" without specifying the adapter interface the stub implements. Phase 0's most important deliverable should be the adapter interface itself, not the stub.
§3 architecture diagram has no explicit adapter layer. Layer 3 ("Symbol Binding and Coverage") is where the adapter sits, but the diagram doesn't show the interface boundary.
The architectural fix. Add a first-class Adapter Interface to the architecture. Something like:
LanguageAdapter (interface):
  language_id: str                                  // "solidity-0.8", "go-1.21"

  # Symbol binding
  resolve_symbol(name: str, context: Context) → ResolvedSymbol
  call_graph(symbol: ResolvedSymbol) → CallGraph
  validate_binding(binding: Binding) → ValidationResult

  # Spec presentation (for LLM-assisted spec extraction later)
  present_to_llm(module: Module) → CanonicalText

  # Trace normalization
  extract_traces(scenario: Scenario) → NormalizedTrace[]

  # Static checks
  symbol_exists(name: str) → bool
  function_signature(symbol: ResolvedSymbol) → Signature
This interface is the architectural contribution. Everything below it (verification backends, IR, dispatcher, status decision) is language-neutral. Everything that ever becomes language-specific lives above this line, in an adapter.
The Solidity adapter is then:

language_id: "solidity-0.8"
resolve_symbol: wraps Slither + solc AST
call_graph: wraps Slither
extract_traces: wraps Foundry + debug_traceTransaction
etc.

The Go adapter, when it comes, is:

language_id: "go-1.21"
resolve_symbol: wraps gopls
call_graph: wraps golang.org/x/tools/go/callgraph
extract_traces: wraps runtime/trace + OpenTelemetry
etc.

The TypeScript adapter is similar with tsserver, etc. Each adapter is plumbing over existing language-specific tooling; the architectural shape never changes.
The Phase 0 implication. Phase 0 must produce two things, not one:

The agnostic core (IR, parser, status decision, evidence aggregator) — already in the plan
The adapter interface specification — currently missing as an explicit deliverable

Phase 0 can ship with a stub adapter (a fake/toy language adapter purely for testing the interface) plus the Solidity adapter starting in Phase 1. The stub adapter is what proves the interface is well-designed: if you can write a null-language adapter that satisfies the interface and the system runs end-to-end against it, the interface is right.
Trace normalization is where the agnostic claim hits real friction. EVM transaction traces and Go runtime traces are semantically different. The plan needs to commit to a NormalizedTrace schema that all adapters project into. From our earlier conversation:
NormalizedTrace = sequence of TraceEvent
TraceEvent:
  timestamp: monotonic
  actor: ActorId           # contract address | goroutine id | thread id
  action: ActionId         # function call | opcode | message
  pre_state: StateSnapshot
  post_state: StateSnapshot
  causal_predecessor: TraceEventId?
  language: LanguageId
  metadata: dict
This schema is the second architectural contribution after the adapter interface. Adapters lose data when normalizing — that's fine — but they must lose it consistently. Phase 0 should define this schema even though only Phase 1's Solidity adapter populates it.
What stays Solidity-first. The shipping order. v1 ships the agnostic architecture plus one adapter (Solidity). v2 ships a second adapter, which is where the agnosticism claim becomes credible because it has been demonstrated, not just promised. The Phase 4 mention of "limited Go adapter" should be reframed: v2 isn't a "limited Go adapter," it's the validation step that proves the interface design held under contact with a fundamentally different language.
What this changes in the document.
Concretely, the revision is:

Insert a new §3.1 "Adapter Interface" between the current §3 and §4, specifying the interface as a first-class architectural element.
Rewrite §7 as "Symbol Binding via Language Adapters" with §7.1 being the interface specification and §7.2+ being Solidity-as-first-implementation.
Rewrite §8 to separate agnostic backends (§8.1–§8.4: Self-Consistency, SMT, TLA+/Model Checking, Static Analysis described agnostically) from adapter responsibilities (each adapter must produce trace data in NormalizedTrace format; each adapter must produce static-analysis output the agnostic Static Analysis backend can consume).
Restructure §14 into §14.1 Phase 0 agnostic tooling + §14.2 Solidity adapter tooling + §14.3 future adapter tooling (template).
Update Phase 0 deliverables in §13 to include:

LanguageAdapter interface specification (docs/adr/0005-language-adapter-interface.md)
NormalizedTrace schema
Stub/null adapter implementing the interface


Update §20 "Strategic Roadmap" to reframe: v1 = agnostic architecture + Solidity adapter; v2 = second adapter validates the interface; v3+ = expanded coverage. The agnosticism is delivered in v1; what scales is the adapter library.

Why this is worth the structural change. Right now, an external reader (or a future engineer joining the project) reads the plan and sees a Solidity tool. The architectural claim of agnosticism is present in the title and §0, then disappears for sections 7-14 where the actual contracts and tools get specified. That's a fragility that will worsen as you build, because the codebase will mirror the document — Solidity-specific code will end up in places that should be agnostic, and the eventual second-adapter work will be a retrofit. Catching this now, before any code exists, is cheap. Catching it in v2 is expensive.
Honest meta-comment. I should have flagged this in the previous vet. The phased "Solidity first, then expand" framing sounded sensible and I accepted it without checking that the architecture of the v1 deliverable preserved the agnostic claim. It didn't, and the document drifted toward describing a Solidity tool with future-language hopes. You caught the drift; the fix is to make the adapter interface a Phase 0 deliverable so the agnostic architecture is what gets built first, even though only one adapter populates it.You said: Revised planRevised planMay 25Claude responded: This is the right revision.Viewed 2 filesViewed 2 filesThis is the right revision. The agnostic positioning is now structural, not rhetorical — the architecture itself preserves the claim rather than just the title. A reader of the current document sees a general-purpose tool with a generic adapter, and only encounters real-ecosystem tooling when reading about future adapters. That's exactly what was missing in the previous version.
What got fixed
The title change to "General-Purpose Build Plan" sets the frame correctly. §0's opening line ("It is not a Solidity tool, a blockchain tool, or a project-specific validator") states the positioning explicitly enough that no reader can drift to the wrong conclusion. §1.3's "Scope Boundary" with explicit lists of what core owns vs. what adapters own is the single most important addition — it establishes the contract that the rest of the document must honor, and the rest of the document does honor it.
§3's architecture diagram now has "Adapter Interface and Symbol Binding" as Layer 3, making the interface a first-class architectural element rather than an implicit detail buried in §7. §7 itself now reads as "this is what an adapter is, here's the interface, here's how Phase 0 satisfies it with a generic one, here's the future expansion path." The interface specification in §7.2 (resolve_symbols, validate_binding, available_evidence, generate_tasks, collect_evidence) is appropriately minimal — five methods, each with a clear job — and matches the layered architecture cleanly.
§8 Verification Backends is now correctly adapter-neutral. The Self-Consistency, SMT, and Model-Checking backends are described in general terms; the Test and Trace backends correctly state that "adapters may expose" these as evidence rather than baking in specific tooling. No more Slither, Foundry, or solc references in the core architecture. The §8.3 and §8.4 framing of "adapters may expose tests/traces as evidence" is the right inversion of responsibility: the backends are agnostic consumers; adapters are language-specific producers.
§14 Phase 0 Tooling is now strictly the agnostic core (Python, Lark, Pydantic, Z3, canonical JSON, pytest). No adapter tooling appears in Phase 0. The previous "Solidity tooling" subsection is gone, replaced by "Future options" that are properly forward-looking rather than current commitments.
The strategic roadmap in §16 is honest: V1 ships the adapter-neutral core, V2 ships one real adapter selected by work priorities, V3 is multiple adapters sharing the same package/evidence/status format, V4 is cross-system requirements only after individual adapters are trustworthy. This is the correct gating discipline.
§13 Phase 1 not pre-selecting Solidity vs. Python vs. Go vs. anything else, and instead listing candidate adapters with selection criteria, is the right move. It defers the adapter decision to when Phase 0's learnings inform it, which is when the decision should actually be made.
The connection back to the broader Attestation Layer is restored in §0 ("a general-purpose component of the Attestation Layer") and §17 ("a work project for a general-purpose Attestation Layer"). The continuity with your existing paper series is now explicit.
The previous-vet items also landed: solo-mode review workflow (§5.5), CLI refusal output example (§15), Phase 0 covering 3 of 6 claim kinds with reasoning (§5.3), source span stability rule (§5.1), architecture diagram direction arrows (§3).
Remaining small items
These are polish, not architecture, but worth fixing before Phase 0 starts.
The adapter interface needs to be a named Phase 0 deliverable. §7.2 has the interface in a code block in the middle of the document. §13's Phase 0 deliverables list mentions "generic symbol-table adapter" but not "adapter interface specification" as a separate artifact. Since the interface is the architectural contribution, it deserves explicit billing — same way the IR JSON Schema is explicitly listed. Recommend adding to Phase 0 deliverables: adapter interface specification (docs/adapter-interface.md + docs/adr/0005-adapter-interface.md). This is what other adapter authors will read; it deserves to exist as a standalone document, not just a section of the build plan.
An adapter conformance suite is missing. If adapters are the extensibility point, there must be a test suite that every adapter must pass to be considered valid. Without this, the Python adapter and the future Go adapter could implement the interface with subtly different semantics and the system would silently fragment. The generic adapter in Phase 0 should serve as the reference implementation that the conformance suite tests against. Recommend adding to Phase 0: adapter conformance test suite (validated by the generic adapter). Future adapter authors run this suite; passing it is the definition of "this adapter is valid."
NormalizedTrace schema is not specified anywhere. §8.4 says "adapters may expose runtime or execution traces" but doesn't define a common format. This will hurt at V3 when the second adapter arrives and its trace format is incompatible with the first. EVM transaction traces, Go runtime traces, Python stack traces, and TypeScript async traces have genuinely different semantics, and projecting them into a shared format is real architectural work that should happen before the second adapter is built, not after. The fix doesn't need to be in Phase 0 — traces aren't part of Phase 0's claim coverage — but the schema should be a named Phase 2 deliverable. Otherwise the V4 cross-system claim is architecturally fragile.
Phase 1 adapter selection needs a forcing function. §13 Phase 1 says "implement one real adapter selected by work priorities" but doesn't specify when this decision must be committed. Open-ended "select later" decisions tend to slip. Recommend: "By the end of Phase 0, the Phase 1 adapter selection is committed in docs/adr/0006-phase-1-adapter-selection.md, justified by Phase 0 learnings about the core. The ADR names the selected ecosystem, the rationale, and the expected adapter-specific tooling." This forces the decision to happen at the right moment — informed by Phase 0 results but before Phase 1 work begins.
Generic adapter evidence semantics are underspecified. §7.3 shows a static symbol table but doesn't say what evidence the generic adapter produces. Just STATICALLY_RESOLVED? Does it have a fake test backend? A fake trace backend? Without specification, you'll discover ambiguities mid-implementation. Recommend a one-paragraph addition: "The generic adapter produces STATICALLY_RESOLVED evidence for symbol resolution and routes SMT-eligible claims through the core SMT backend with encoded predicates from the symbol table. It does not produce TEST_VALIDATED or TRACE_VALIDATED evidence; those require a real adapter." This bounds Phase 0 cleanly.
JSON Schema commitment. §5.4 ends "The full JSON Schema is a Phase 0 deliverable. Inline examples are explanatory, not the schema contract." Good. Worth adding: "The schema lives at schemas/requirement-ir-0.1.schema.json and is regenerated from the Pydantic models on every build. CI fails if the committed schema drifts from the generated one." This makes the schema synthesis reproducible and prevents the inline examples and the actual schema from diverging.
Verdict
The plan is now buildable as a general-purpose Attestation Layer component, not a Solidity tool wearing a generic title. The architectural commitments match the positioning. Phase 0 deliverables exercise the full pipeline through a generic adapter, which proves the interface contract before any real adapter is invested in.
The next move is implementation. The four ADRs from the previous vet (tooling, IR versioning, LLM rewrite approval, status purity) plus the two new ones I'd add (adapter interface, Phase 1 adapter selection) are six one-page documents totaling maybe a day of writing. After that you have the contracts, the schemas, the grammar, and the status decider — which is roughly Week 1 of Phase 0 done.
Build it.