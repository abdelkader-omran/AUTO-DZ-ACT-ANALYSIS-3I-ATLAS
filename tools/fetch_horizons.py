validate_record = getattr(mod, "validate_record", None)
if not callable(validate_record):
    return False, ["validate_record() not found or not callable in validator"]
ok, msgs = validate_record(record_path)  # type: ignore
