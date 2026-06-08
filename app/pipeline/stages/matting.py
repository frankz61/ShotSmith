def run(input_path, storage, task_id: str, provider) -> str:
    out_dir = storage.task_dir(task_id) / "03_cutout"
    res = provider.cutout(str(input_path), str(out_dir))
    return res.rgba_path
