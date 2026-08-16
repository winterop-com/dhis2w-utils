# Category combo builder

Declarative one-call helper that takes a typed `CategoryComboBuildSpec` (categories + their options) and materialises the entire Categories → CategoryCombo → CategoryOptionCombo tree against DHIS2. Wraps `client.categories`, `client.category_options`, `client.category_combos`, and (on v43) the COC-regen wait helper into a single idempotent call.

```python
from dhis2w_client import CategoryComboBuildSpec, CategorySpec, CategoryOptionSpec, build_category_combo

spec = CategoryComboBuildSpec(
    name="Sex x Age",
    categories=[
        CategorySpec(
            name="Sex",
            short_name="Sex",
            options=[
                CategoryOptionSpec(name="Male", short_name="M"),
                CategoryOptionSpec(name="Female", short_name="F"),
            ],
        ),
        CategorySpec(
            name="Age band",
            short_name="Age",
            options=[
                CategoryOptionSpec(name="<1y", short_name="<1y"),
                CategoryOptionSpec(name=">=1y", short_name=">=1y"),
            ],
        ),
    ],
)
result: CategoryComboBuildResult = await build_category_combo(client, spec)
print(result.category_combo_uid, result.category_option_combo_uids)
```

Idempotent on name — if a category / option with the requested name already exists it's reused rather than duplicated. On v43 the helper waits for the COC matrix to materialise before returning (so callers can immediately start writing data values against it).

Worked example: [`examples/client/category_combo_build.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/category_combo_build.py).

::: dhis2w_client.v42.category_combo_builder
