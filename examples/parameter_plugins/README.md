# Trusted numerical extension example

`native_median_absolute_deviation.py` adds a new mathematical method without
modifying the import, plotting, review or report code. It uses original valid
observations and explicitly labels sample weighting. It does not assume a time
coordinate, physical meaning or a normal distribution.

1. Open **Tools → Presets / Extensions** and install the Python example through the
   application's existing trusted extension workflow.
2. Open **More Tools → Analyse & Compare Recordings…**, choose an analog or unknown
   numeric field, and run the analysis.
3. Find `example.native_mad` in the result and in the exported metric evidence.
4. Disable the extension in the same tool to restore the built-in capability set.

Python extensions are executable code. Install only code you have reviewed and
trust. Reader values, profile JSON and source-file function names are never
imported or executed as Python code.

The entry point is `register_patch(manager)`. Register a `CapabilityDefinition`
and a callable through `manager.register_analyser(definition, function)`. The
callable receives `(projection, context)`; call `context.emit(metric_id, value,
unit, weighting=..., evidence_basis=...)` to produce the shared versioned record.
Call `context.check()` in long loops to cooperate with cancellation. Native
arrays, original source indices, validity and the reviewed mapping are in the
context. The definition advertises accepted structures, optional role/dimension
gates, prerequisites, scopes, output units and support policy.

Registration rejects conflicting identifiers and invalid callables. A failed
extension registration rolls back all hooks and capabilities from that extension;
a failed analyser becomes an explicit error record while other measurements
remain available. Disabling or removing an extension reloads the same built-in
set used by installed and standalone editions.

A new role that uses existing mathematics needs no Python extension: assign an
open role identifier in a schema-2 profile, confirm its units/meaning/encoding,
and configure existing operations such as named dwell bands under
`mapping.parameters.bands`. Role-specific integration can be requested through
`mapping.parameters.operations` (`integrate_flow`, `integrate_active_power`,
`rotation`, `waveform`); each operation still checks dimensions, acquisition
support and reviewed signal kind. A label alone never enables a physical claim.
