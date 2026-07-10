from pathlib import Path

def compose(f, g):
  return lambda x: f(g(x))

def join_path(dir, file):
  return Path(dir) / file

class Repository:
  def __init__(self, name, full_name, clone_url, blobs_url, default_branch):
    self.name = name
    self.full_name = full_name
    self.clone_url = clone_url
    self.blobs_url = blobs_url
    self.default_branch = default_branch

def file_name(file_json):
  return file_json["path"].split('/')[-1]