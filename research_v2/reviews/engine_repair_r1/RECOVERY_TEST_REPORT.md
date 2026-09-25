# Recovery test report

The formal workflow was exercised with a synthetic run. Reservation writes run identity, hashes, data identity, parameters, command, start time, process identity and execution attempt before execution. Completed runs return existing state without rerunning. Unknown existing output is rejected. Windows denied process command line inspection, so identity remains UNKNOWN_ACCESS_DENIED; no process was started or terminated.
