"""Standard compact form widget attributes for ChurchHub templates."""


def _join_classes(*parts):
    return " ".join(p for p in parts if p)


def input_attrs(**extra):
    """Small text-like inputs."""
    css = extra.pop("class", "")
    return {"class": _join_classes("form-control", "form-control-sm", css), **extra}


def select_attrs(**extra):
    """Small select dropdowns."""
    css = extra.pop("class", "")
    return {"class": _join_classes("form-select", "form-control-sm", css), **extra}


def textarea_attrs(**extra):
    css = extra.pop("class", "")
    rows = extra.pop("rows", 3)
    return {"class": _join_classes("form-control", "form-control-sm", css), "rows": rows, **extra}


def search_attrs(**extra):
    css = extra.pop("class", "")
    return {
        "class": _join_classes("form-control", "form-control-sm", "field-search", css),
        "placeholder": extra.pop("placeholder", "Search…"),
        **extra,
    }


def checkbox_attrs(**extra):
    css = extra.pop("class", "")
    return {"class": _join_classes("form-check-input", css), **extra}
