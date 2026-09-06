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

def extention_case_variations(filename : str):
  split = filename.split('.')
  if len(split) > 1:
    return ['.'.join(split[:-1] + [ext]) for ext in [split[-1].upper(), split[-1].lower()]]
  else:
    return [filename]

def reponameless_path(filepath):
  return '/'.join(filepath.split('/')[1:])
def reponameless_path_json(file_json):
  return '/'.join(file_json['path'].split('/')[1:])

from enum import Enum
class CompilerTypes(Enum):
  FXC = 0
  DXC = 1

def file_stats(repo_stats, file_json):
  return file_stats_key(repo_stats, _file_key(file_json))

def file_stats_key(repo_stats, file_key):
  return repo_stats[file_key]

def _make_file_key(file_path : str):
  return file_path.lower()


def _file_key(file_json):
  return _make_file_key(file_json['path'])

from itertools import chain
def flatten_uniquely(vlist):
  return list(set(chain.from_iterable(vlist)))

_shader_types = ["pixel", "vertex", "compute"]
_shader_types_ext = _shader_types + ['library']

def empty_dict_if_absent(dictionary : dict, key):
  return dictionary.setdefault(key, {})

class Decompilers(Enum):
  RGA = 'rga'
  ISA = 'isa'
  Ocloc = 'ocloc'