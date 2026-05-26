; Phase 0 SMT query for REQ-AUTH-001
(declare-const authorized_actor Bool)
(assert (not authorized_actor))
(check-sat)
