import { useEffect, useRef, useState } from "react";

// Manages options + loading/error state for every "dynamic-select" input in
// `inputs`, reloading (and clearing the field's current value) whenever the
// input it `dependsOn` changes. Handles arbitrarily long dependency chains
// (e.g. Environment -> Master Account -> Tenant -> Cloud Account): each
// dynamic-select only resets/reloads when *its own* dependency's value has
// actually changed since the last run (tracked in `prevDependencyValues`) —
// not whenever the combined key changes for any reason. Without that check,
// selecting a value at one level would re-run the effect for every level at
// once and immediately blank out the selection the user just made, since
// a naive version resets every dynamic field on any change to the joined
// key rather than just the one field whose dependency moved. A change
// upstream still cascades downstream correctly, just one render at a time:
// resetting a field's value changes what its own dependents see as their
// dependency, which is what triggers *their* reset on the next render.
//
// `input.loadOptions(dependencyValue, values)` gets the full `values` object
// as a second argument too, for a loader that needs more than just its
// immediate dependency (e.g. a region picked further up the chain).
export function useDynamicSelectOptions(inputs, values, setValues) {
  const [dynamicOptions, setDynamicOptions] = useState({});
  const prevDependencyValues = useRef({});

  const dynamicInputs = inputs.filter((input) => input.type === "dynamic-select" && input.dependsOn);
  const dynamicDependencyKey = dynamicInputs.map((input) => `${input.name}=${values[input.dependsOn] ?? ""}`).join("|");

  useEffect(() => {
    for (const input of dynamicInputs) {
      const dependencyValue = values[input.dependsOn];
      if (prevDependencyValues.current[input.name] === dependencyValue) continue;
      prevDependencyValues.current[input.name] = dependencyValue;

      setValues((prev) => ({ ...prev, [input.name]: "" }));

      if (!dependencyValue) {
        setDynamicOptions((prev) => ({ ...prev, [input.name]: { loading: false, error: null, options: [] } }));
        continue;
      }

      setDynamicOptions((prev) => ({ ...prev, [input.name]: { loading: true, error: null, options: [] } }));
      input
        .loadOptions(dependencyValue, values)
        .then((options) => {
          setDynamicOptions((prev) => ({ ...prev, [input.name]: { loading: false, error: null, options } }));
        })
        .catch((err) => {
          setDynamicOptions((prev) => ({ ...prev, [input.name]: { loading: false, error: err.message, options: [] } }));
        });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dynamicDependencyKey]);

  return dynamicOptions;
}
