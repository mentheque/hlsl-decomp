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

import re
def _compile_dict_patterns(dict, ignorecase = True):
  ret_dict = {}
  for key, patterns in dict.items():
    ret_dict[key] = [(re.compile(pattern, re.IGNORECASE if ignorecase else re.NOFLAG), value)
                     for pattern, value in patterns]

  return ret_dict

_platforms = ["ReShade", "Unity", "UnrealEngine", "Ogre3D", "MS FX"]
_pfilename_patterns = _compile_dict_patterns(
  {
    'ReShade' : [(r'reshade', 0.90)],
    'Unity' : [(r'\.cginc$', 0.90)],
    'UnrealEngine' : [(r'\.ush$', 0.95), (r'\.usf$', 0.95)]
  }
)
_pcontents_patterns = _compile_dict_patterns(
  {
    'ReShade' : [(r'#include\s*"ReShade\.fxh"', 0.9),
                 (r'defined\s*\(\s*__RESHADE__\s*\)', 0.9),
                 (r'ui_(label|type|category|min|max)', 0.8),
                 (r'RESHADE', 0.2)],
    'Unity'   : [(r'(CG|HLSL)PROGRAM', 0.9),
                 (r'#pragma\s+(vertex|fragment|geometry|hull|domain|compute)', 0.9),
                 (r'UNITY_[A-Z_]+', 0.9),
                 (r'CBUFFER_(START|END)', 0.8)],
    'Ogre3D'  : [(r'#include\s*<OgreUnifiedShader\.h>', 0.9)],
    'MS FX'   : [(r'^\s*technique(10|11)?\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\{', 0.9),
                 (r'^\s*pass\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\{', 0.9),
                 (r'^\s*pass\s*\{', 0.9),
                 (r'compile\s+(vs|ps)_[0-9]_[0-9]', 0.8),
                 (r'CompileShader\s*\(', 0.8),
                 (r'Set(Vertex|Pixel|Geometry|Domain|Hull)Shader\s*\(', 0.8),
                 (r'(BlendState|DepthStencilState|RasterizerState)', 0.8)]
  }
)

def _test_categorical_patterns(categories, filename_patterns, contents_patterns, filename : str, file_contents : str):
  def _test_str_against_dictionary(to_test: str, dict, category : str):
    if category in dict:
      for pattern, value in dict[category]:
        if pattern.search(to_test) is not None:
          return value
    return 0

  results = {}
  for category in categories:
    results[category] = _test_str_against_dictionary(filename, filename_patterns, category) \
                        + _test_str_against_dictionary(file_contents, contents_patterns, category)

  if any([r > 0 for r in results.values()]):
    print("WOW!!!!!")
    print(filename, results)
  return results

def _test_platforms(filename : str, file_contents: str):
  return _test_categorical_patterns(_platforms, _pfilename_patterns, _pcontents_patterns, filename, file_contents)


from license_scanning import file_path
from utils import file_name
# hash, size, line count
#
# TODO: Add license groups in here too somehow for uniformity
def _calculate_file_stats(config : Config, repo : Repository, file_json):
  filepath = file_path(config, repo, file_json)
  normalised_contents = _normalise(filepath)
  return {
    'hash': _hash(normalised_contents),
    'size': filepath.stat().st_size,
    'lines': len(normalised_contents.split('\n')),
    'platforms': _test_platforms(file_name(file_json), normalised_contents)
  }


import os
from pathlib import Path
def _includes_list(config : Config, repo : Repository, file_jsons):
  includes = {}

  # initial pass
  for file_json in file_jsons:
    filepath = file_path(config, repo, file_json)
    relative_dir = os.path.dirname(file_json['path'])
    incset = includes[file_json['path']] = set()
    normalised_contents = ""
    try:
      normalised_contents = _normalise(filepath)
    except Exception as e:
      normalised_contents = ""

    for line in normalised_contents.split('\n'):
      stripped = line.strip()
      if stripped.startswith("#include"):
        match = re.search(r'#include\s*"([^"]+)"|#include\s*<([^>]+)>', stripped)
        if match:
          inc_path = match.group(1) if match.group(1) else match.group(2)
          incset.add(Path(os.path.normpath(os.path.join(relative_dir, inc_path))).as_posix())

  updated = True
  while updated:
    updated = False
    for incset in includes.values():
      init_incset = incset.copy()
      init_size = len(init_incset)
      for include in init_incset:
        if include in includes:
          incset.update(includes[include])
          if len(incset) > init_size:
            updated = True

  return includes




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


# Where to get jsons?
def update_stats(config : Config, repo : Repository, file_jsons, recalculate : bool = False):
  repo_stats = {}
  def _merge_stats_with_includes(file_key):
    file_stats = repo_stats[file_key]
    includes = file_stats['includes']
    for include in includes:
      if include in repo_stats:
        platform_stats = repo_stats[include]['platforms']
        for platform in _platforms:
          file_stats['platforms'][platform] = max(file_stats['platforms'][platform], platform_stats[platform])
  try:
    repo_stats = load_repo_stats(config, repo)
  except Exception as e:
    repo_stats = {}

  includes = _includes_list(config, repo, file_jsons)

  changed = False
  failed = []
  for file_json in file_jsons:
    file_key = file_json['path']
    if (file_key in repo_stats and recalculate) or file_key not in repo_stats:
      try:
        repo_stats[file_key] = _calculate_file_stats(config, repo, file_json)
        #Doesn't work somehow, even when the one above seem to assign the 4
        repo_stats[file_key]['includes'] = list(includes[file_key])
        changed = True
      except Exception as e:
        config.log.licenses.secondary(f"Failed to calculated stats for {file_key}")
        config.log.licenses.secondary(str(e))
        failed.append(file_json)

  for file_json in file_jsons:
    file_key = file_json['path']
    _merge_stats_with_includes(file_key)
    changed = True # I guess it's always True now, whatever

  config.log.licenses.primary(f"Stats for {repo.name},"
                              f" total {len(file_jsons)},"
                              f" success: {len(file_jsons) - len(failed)}, failed: {len(failed)}")

  if changed:
    _save_repo_stats(config, repo, repo_stats)

def file_stats(repo_stats, file_json):
  return repo_stats[file_json['path']]