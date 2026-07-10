import json

from config import Config
from utils import Repository

import hashlib

def _normalise(file):
  with open(file, 'r', encoding='utf-8') as f:
    content = f.read()

  normalized = content.replace('\r\n', '\n').replace('\r', '\n') # line endings
  normalized = '\n'.join(line.rstrip() for line in normalized.split('\n')) # trailing spaces
  return normalized

def _hash(file_contents : str):
  return hashlib.sha256(file_contents.encode()).hexdigest()

def _combine_dicts(dict1, dict2, lmbd):
  ret = dict()
  for key in dict1.keys():
    ret[key] = lmbd(dict1[key], dict2[key])

  return ret

def _add_dicts(dict1, dict2):
  return _combine_dicts(dict1, dict2, (lambda x, y : x + y))

def _test_filename(filename):

  _profile_patterns = {
    (r'\.ps(_[0-9]_[0-9])?\.$', 'pixel_shader', 0.85),
    (r'_ps\.', 'pixel_shader', 0.85),
    (r'_fs\.', 'pixel_shader', 0.85),
    (r'_pixel\.', 'pixel_shader', 0.85),
    (r'_fragment\.', 'pixel_shader', 0.85),
    (r'PixelShader', 'pixel_shader', 0.75),
    (r'FragmentShader', 'pixel_shader', 0.75),

    (r'\.vs(_[0-9]_[0-9])?\.$', 'vertex_shader', 0.85),
    (r'_vs\.', 'vertex_shader', 0.85),
    (r'_vertex\.', 'vertex_shader', 0.85),
    (r'VertexShader', 'vertex_shader', 0.75),

    (r'\.cs(_[0-9]_[0-9])?\.$', 'compute_shader', 0.85),
    (r'_cs\.', 'compute_shader', 0.85),
    (r'_compute\.', 'compute_shader', 0.85),
    (r'ComputeShader', 'compute_shader', 0.75),


  }

  _platform_patterns = {
    (r'reshade', 'ReShade', 0.90),
    (r'\.cginc$', 'Unity', 0.90),
    (r'\.ush$', 'UnrealEngine', 0.95),
    (r'\.usf$', 'UnrealEngine', 0.95)
  }

from license_scanning import file_path
# hash, size, line count
def _calculate_file_stats(config : Config, repo : Repository, file_json):
  filepath = file_path(config, repo, file_json)
  normalised_contents = _normalise(filepath)
  return {
    'hash': _hash(normalised_contents),
    'size': filepath.stat().st_size,
    'lines': len(normalised_contents.split('\n'))
  }

from utils import join_path
# TODO: fix copypaste from scancode_cache_file
def _repo_shader_stats_file(config : Config, repo : Repository):
  # Now, it is possible to fool this pattern if there is _ in the names of user/repo, but
  # that's unlikely enough for me not to bother, and I don't whant more directory hirarchy.
  return join_path(config.shader_stats_dir, repo.full_name.replace('/', '_') + '.json')

def load_repo_stats(config : Config, repo : Repository):
  try:
    with open(_repo_shader_stats_file(config, repo), "r") as f:
      return json.load(f)
  except Exception as e:
    config.log.licenses.primary(f"Unable to load {repo.full_name} stats, returning empty")
    return {}

def _save_repo_stats(config : Config, repo : Repository, repo_stats):
  path = _repo_shader_stats_file(config, repo)
  path.parent.mkdir(parents=True, exist_ok=True)
  with open(_repo_shader_stats_file(config, repo), "w") as f:
    json.dump(repo_stats, f)

def update_stats(config : Config, repo : Repository, file_jsons, recalculate : bool = False):
  repo_stats = {}
  try:
    repo_stats = load_repo_stats(config, repo)
  except Exception as e:
    repo_stats = {}

  changed = False
  failed = []
  for file_json in file_jsons:
    file_key = file_json['path']
    if (file_key in repo_stats and recalculate) or file_key not in repo_stats:
      try:
        repo_stats[file_key] = _calculate_file_stats(config, repo, file_json)
        changed = True
      except Exception as e:
        config.log.licenses.secondary(f"Failed to calculated stats for {file_key}")
        config.log.licenses.secondary(str(e))
        failed.append(file_json)

  config.log.licenses.primary(f"Stats for {repo.name},"
                              f" total {len(file_jsons)},"
                              f" success: {len(file_jsons) - len(failed)}, failed: {len(failed)}")

  if changed:
    _save_repo_stats(config, repo, repo_stats)

def _file_stats(repo_stats, file_json):
  return repo_stats[file_json['path']]

def filter_has_stats(repo_stats, file_json):
  return file_json['path'] not in repo_stats

def _filter_between(value, min_value, max_value):
  return (min_value is not None and value < min_value) or (max_value is not None and value > max_value)

def _filter_stat_between(stats_name, min_value, max_value):
  return (lambda repo_stats, file_json:
          _filter_between(_file_stats(repo_stats, file_json)[stats_name], min_value, max_value))

def new_filter_line_count(min_lines = None, max_lines = None):
  return _filter_stat_between('lines', min_lines, max_lines)

def new_filter_size(min_size = None, max_size = None):
  return _filter_stat_between('size', min_size, max_size)

def new_filter_unique_hash(config : Config):
  encountered = {}
  def filter(repo_stats, file_json):
    hash = _file_stats(repo_stats, file_json)['hash']
    if hash in encountered:
      #config.log.licenses.secondary(f"Hash collision: {encountered[hash]}, {file_json['path']}")
      return True
    else:
      encountered[hash] = file_json['path']
      return False

  return filter

def new_filter_file_extensions(target_extensions):
  def filter(repo_stats, file_json):
    path_str = file_json['path']
    return not any(path_str.endswith('.' + extension) for extension in target_extensions)

  return filter


def filter(config : Config, walked, filters):
  filtered = []
  for repo, file_license_pairs in walked:
    repo_stats = load_repo_stats(config, repo)
    repo_filtered = []
    for file, license in file_license_pairs:
      if not any(filter(repo_stats, file) for filter in filters):
        repo_filtered.append((file, license))

    if len(repo_filtered) > 0:
      filtered.append((repo, repo_filtered))

  return filtered




