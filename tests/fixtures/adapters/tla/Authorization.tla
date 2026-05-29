---- MODULE Authorization ----
EXTENDS Naturals

VARIABLE stateChanged

Init == stateChanged = FALSE
Next == UNCHANGED stateChanged
UnauthorizedRejectedBeforeStateChange == stateChanged = FALSE

====
