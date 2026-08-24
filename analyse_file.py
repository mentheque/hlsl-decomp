import json

from config import Config
from utils import Repository, file_stats, file_stats_key, _file_key, _make_file_key

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
def _compile_dict_patterns(dict, flags = re.IGNORECASE):
  ret_dict = {}
  for key, patterns in dict.items():
    ret_dict[key] = [(re.compile(pattern, flags), value)
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

# TODO: redo basic stats calculations, changed some patterns
_pcontents_patterns = _compile_dict_patterns(
  {
    'ReShade' : [(r'#include\s*"ReShade\.fxh"', 0.9),
                 (r'defined\s*\(\s*__RESHADE__\s*\)', 0.9),
                 (r'ui_(label|type|category|min|max)', 0.8),
                 (r'RESHADE', 0.2)],
    'Unity'   : [(r'(CG|HLSL)PROGRAM', 0.9),
                 (r'#pragma\s+(vertex|fragment|geometry|hull|domain|compute)', 0.9),
                 (r'UNITY_[A-Z_]+', 0.9),
                 (r'CBUFFER_(START|END)', 0.8),
                 (r'#if\s+SHADERPASS\s*!=', 0.8),
                 (r'SHADERPASS_\w+', 0.8),
                 (r'com.unity', 0.8),
                 (r'\.cginc', 0.8)], # if .cginc includes are external and thus cannot pass evaluation down
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

from utils import _shader_types
_stfilename_patterns = _compile_dict_patterns({
  "pixel": [(r'\.ps', 0.9),
            (r'\.pixel', 0.9),
            (r'ps_', 0.9),
            (r'pixel_', 0.8),
            (r'_ps2x', 0.8)],
  "vertex": [
    (r'\.vs', 0.9),
    (r'\.vert', 0.9),
    (r'\.vertex', 0.9),
    (r'\.vsh', 0.9),
    (r'vs_', 0.9),
    (r'vert_', 0.9),
    (r'vertex_', 0.8)
  ],
  "compute" : [
    (r'\.cs', 0.9),
    (r'\.compute', 0.9),
    (r'\.csh', 0.9),
    (r'cs_', 0.9),
    (r'csh_', 0.9),
    (r'compute_', 0.8)
  ]
})

_stcontents_patterns = _compile_dict_patterns({
  "pixel": [
    (r':\s*SV_Target\b', 0.95),
    (r':\s*SV_Target\d+\b', 0.95),
    (r':\s*SV_Target\s*\[\s*\d+\s*\]', 0.95),
    (r'\b(discard|kill)\s*[;\(]', 0.89),
    (r'\b(Clip|Discard)\s*\(', 0.89),
    (r':\s*SV_Depth\b', 0.88),
    (r':\s*SV_DepthGreater\b', 0.88),
    (r':\s*SV_DepthLessEqual\b', 0.88),
  ],
  "vertex": [
    (r':\s*SV_VertexID\b', 0.9),
    (r':\s*SV_InstanceID\b', 0.9),
    (r':\s*BLENDWEIGHT\b', 0.89),
    (r':\s*BLENDINDICES\b', 0.89),
    (r':\s*BLENDWEIGHT\d+\b', 0.89),
    (r':\s*BLENDINDICES\d+\b', 0.89),
    (r'(in|inout)\s+\w+\s+\w+\s*:\s*POSITION\b', 0.88),
  ],
  "compute" : [
    (r'\[numthreads\s*\(', 0.95),
    (r':\s*SV_DispatchThreadID\b', 0.9),
    (r':\s*SV_GroupThreadID\b', 0.9),
    (r':\s*SV_GroupID\b', 0.9),
    (r':\s*SV_GroupIndex\b', 0.9),
    (r'\bgroupshared\b', 0.9),
    (r'GroupMemoryBarrierWithGroupSync\s*\(', 0.9),
    (r'DeviceMemoryBarrierWithGroupSync\s*\(', 0.9),
    (r'AllMemoryBarrierWithGroupSync\s*\(', 0.9),
    (r'GroupMemoryBarrier\s*\(', 0.9),
  ]
})

def _test_shader_types(filename : str, file_contents: str):
  return _test_categorical_patterns(_shader_types, _stfilename_patterns, _stcontents_patterns, filename, file_contents)

def _is_target_extention(config: Config, filename):
  return any(pattern.match(filename) for pattern in config.target_extension_patterns)

from license_scanning import file_path
from utils import file_name
# hash, size, line count
#
# TODO: Add license groups in here too somehow for uniformity
def _calculate_file_stats(config : Config, repo : Repository, file_json):
  filepath = file_path(config, repo, file_json)
  normalised_contents = _normalise(filepath)
  filename = file_name(file_json)
  return {
    'hash': _hash(normalised_contents),
    'size': filepath.stat().st_size,
    'lines': len(normalised_contents.split('\n')),
    'platforms': _test_platforms(filename, normalised_contents),
    'shader_type': _test_shader_types(filename, normalised_contents),
    'is_shader': _is_target_extention(config, filename),
    'case_sensitive_path' : file_json['path']
  }


import os
from pathlib import Path
from utils import extention_case_variations

# Creates flat lists of all includes for all the files in the current repository,
# Containing all (possibly) included files from the same repository
def _includes_list(config : Config, repo : Repository, file_jsons):
  includes = {}

  # initial pass
  for file_json in file_jsons:
    filepath = file_path(config, repo, file_json)
    relative_dir = os.path.dirname(file_json['path'])
    # Again, some repos expect case-insensitivity for includes, so making all lower.
    incset = includes[_file_key(file_json)] = set()
    normalised_contents = ""
    try:
      normalised_contents = _normalise(filepath)
    except Exception as e:
      normalised_contents = ""

    # To handle blocks of cpp includes.
    ifstack = [True]

    for line in normalised_contents.split('\n'):
      stripped = line.strip()
      if stripped.startswith("#if"):
        if re.match(r'#ifdef\s+__cplusplus\b', stripped):
          ifstack.append(False)
        elif re.match(r'^\s*#ifndef\s+__cplusplus\b', stripped):
          ifstack.append(True)
        else:
          ifstack.append(ifstack[-1])
      elif stripped.startswith('#endif'):
        ifstack.pop()
        if len(ifstack) == 0:
          config.log.licenses.primary(f"File {filepath} has broken #if directive hierarchy. Aborting include search.")
          break
      elif ifstack[-1] and stripped.startswith("#include"):
        match = re.search(r'#include\s*"([^"]+)"|#include\s*<([^>]+)>', stripped)
        if match:
          inc_path = match.group(1) if match.group(1) else match.group(2)
          # Again, some repos expect case-insensitivity for includes, so making all lower.
          incset.add(
            _make_file_key(
              Path(os.path.normpath(os.path.join(relative_dir, inc_path))).as_posix()
            )
          )

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


_license_fields = ['license', 'worst_included_license']
def load_repo_stats(config : Config, repo : Repository):

  try:
    with open(_repo_shader_stats_file(config, repo), "r") as f:
      loaded = json.load(f)
      for license_field in _license_fields:
        for file_loaded in loaded.values():
          if license_field in file_loaded:
            file_loaded[license_field] = LicenseGroup(file_loaded[license_field])
      return loaded
  except Exception as e:
    config.log.licenses.primary(f"Unable to load {repo.full_name} stats, returning empty")
    return {}

def _save_repo_stats(config : Config, repo : Repository, repo_stats):
  path = _repo_shader_stats_file(config, repo)
  path.parent.mkdir(parents=True, exist_ok=True)
  for file_stat in repo_stats.values():
    for license_field in _license_fields:
      if license_field in file_stat:
        file_stat[license_field] = file_stat[license_field].value

  with open(_repo_shader_stats_file(config, repo), "w") as f:
    json.dump(repo_stats, f)



def update_basic_stats(config : Config, repo : Repository, file_jsons, recalculate : bool = False):
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
    # Code is primarily written for and on Windows I guess, so some files expect
    # case-insensitive include logic, so adding that here.
    file_key = _file_key(file_json)
    if (file_key in repo_stats and recalculate) or file_key not in repo_stats:
      try:
        repo_stats[file_key] = _calculate_file_stats(config, repo, file_json)
        repo_stats[file_key]['includes'] = list(includes[file_key])
        changed = True
      except Exception as e:
        config.log.licenses.secondary(f"Failed to calculated stats for {file_key}")
        config.log.licenses.secondary(str(e))
        failed.append(file_json)

  for file_json in file_jsons:
    file_key = _file_key(file_json)
    # To not go over failed files
    if file_key in repo_stats:
      _merge_stats_with_includes(file_key)
      changed = True # I guess it's always True now, whatever

  config.log.licenses.primary(f"Stats for {repo.name},"
                              f" total {len(file_jsons)},"
                              f" success: {len(file_jsons) - len(failed)}, failed: {len(failed)}")

  if changed:
    _save_repo_stats(config, repo, repo_stats)

from license_scanning import _sort_file_conclusive, _filter_file_conclusive
from config import LicenseGroup
def calculate_license_stats(config : Config, walked):
  config.log.licenses.primary("Saving file licenses")
  permissive, gpl, nonedet, other = \
    _sort_file_conclusive(config, _filter_file_conclusive(walked, store_empty_repos=True), store_empty_repos=True)
  for i in range(len(permissive)):
    repo = walked[i][0]
    repo_stats = load_repo_stats(config, repo)

    config.log.licenses.secondary(f"Saving file licenses for {repo.full_name}")

    # Some files from file_jsons may be missing if errored on basic stat calculations, so ignoring them here
    for file_stat in repo_stats.values():
      file_stat['license'] = LicenseGroup.Inconclusive # For files with license tracing to
      # several (0) equal sources. For others will be overwritten. Technically can be determined directly already here,
      # but this works too.

    for license_group, repos_n_files in [(LicenseGroup.Permissive, permissive), (LicenseGroup.GPL, gpl),
                                         (LicenseGroup.Unidentified, nonedet), (LicenseGroup.Other, other)]:
      for file_json, _ in repos_n_files[i][1]:
        # Some files from file_jsons may be missing if errored on basic stat calculations, so ignoring them here
        if _file_key(file_json) in repo_stats:
          file_stats(repo_stats, file_json)['license'] = license_group

    for file_stat in repo_stats.values():
      file_stat['worst_included_license'] = \
        max([repo_stats[included]['license'] if included in repo_stats else LicenseGroup.ExternalFile
             for included in file_stat['includes']], key=lambda m: m.value, default=LicenseGroup.NoIncludes)

    _save_repo_stats(config, repo, repo_stats)

def _compile_ep_patterns(patterns, flags = re.IGNORECASE | re.DOTALL):
  ret = {}
  for shader_type in _shader_types:
    ret[shader_type] = [re.compile(pattern, flags) for pattern in patterns[shader_type]]

  return ret

from utils import CompilerTypes, flatten_uniquely
_entry_point_patterns = _compile_ep_patterns({
  'pixel': flatten_uniquely([
    [
      rf'\b\w+\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)\s*:\s*{indicator}\b',
      rf'\b\w+\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)\s*:\s*{indicator}\d+\b',
      rf'\bvoid\s+([a-zA-Z_]\w*)\s*\(([^)]*out\s+\w+\s+\w+\s*:\s*{indicator}[^)]*)\)',
      rf'\b\w+\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)\s*:\s*{indicator}\d*\b',
      rf'\bvoid\s+([a-zA-Z_]\w*)\s*\(([^)]*,\s*out\s+\w+\s+\w+\s*:\s*{indicator}\b[^)]*)\)'
    ] for indicator in ['SV_Target', 'SV_Depth', 'COLOR']
  ]),
  'vertex': flatten_uniquely([
      [
        rf'\b\w+\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)\s*:\s*{indicator}\b',
        rf'\b\w+\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)\s*:\s*{indicator}\d+\b',
        rf'\bvoid\s+([a-zA-Z_]\w*)\s*\(([^)]*out\s+\w+\s+\w+\s*:\s*{indicator}[^)]*)\)',
        rf'\b\w+\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)\s*:\s*{indicator}\d*\b',
        rf'\bvoid\s+([a-zA-Z_]\w*)\s*\(([^)]*,\s*out\s+\w+\s+\w+\s*:\s*{indicator}\b[^)]*)\)'
      ] for indicator in ['SV_Position', 'POSITION', 'SV_VertexID', 'VERTEXID', 'SV_InstanceID', 'INSTANCEID']
    ]),
  'compute': flatten_uniquely([
    [
        r'\[numthreads\s*\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)\s*\]\s*(?:\w+\s+)?([a-zA-Z_]\w*)\s*\(([^)]*)\)',
        r'\[numthreads\s*\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)\s*\]\s*\n\s*(?:\w+\s+)?([a-zA-Z_]\w*)\s*\(([^)]*)\)',
    ]
    + [
        rf'\b\w+\s+([a-zA-Z_]\w*)\s*\(([^)]*{semantic}[^)]*)\)'
        for semantic in ['SV_DispatchThreadID', 'SV_GroupThreadID', 'SV_GroupID', 'SV_GroupIndex']
    ]
  ])
})

_default_ep_values = {
  'pixel' : ['main'],
  'vertex' : ['main'],
  'compute' : ['main']
}

_comptarget_prefix = {
  'pixel' : 'ps',
  'vertex' : 'vs',
  'compute' : 'cs'
}

_comptarget_patterns = _compile_ep_patterns({
    shader_type : [rf'{_comptarget_prefix[shader_type]}_\d+_[x\d]+']
    for shader_type in _shader_types
  },
  flags=0
)





from collections import defaultdict
def calculate_vanilla_compilation_parameters(config : Config, walked, specific_shader_types = None,
                                             excluded_repos : list = None, included_repos : list = None):
  from compile import load_preprocessed_file
  selected_shader_types = _shader_types if specific_shader_types is None else specific_shader_types
  def default_if_absent(dictionary, key, value):
    if key not in dictionary:
      dictionary[key] = value
    return dictionary[key]


  filter = lambda x : True
  if excluded_repos is not None:
    filter = lambda x: x not in excluded_repos
  if included_repos is not None:
    filter = lambda x: x in included_repos

  def detect_pixel_ep(contents):
    struct_patterns = [r'\bstruct\s+(\w+)\s*\{[^}]*SV_Target[^}]*\}', r'\bstruct\s+(\w+)\s*\{[^}]*:\s*COLOR[^}]*\}']
    structs = flatten_uniquely(
      [re.findall(struct_pattern, contents, re.IGNORECASE | re.DOTALL) for struct_pattern in struct_patterns])

    #TODO: fix copypaste
    patterns = flatten_uniquely([
      [rf'\b{struct_name}\s+([a-zA-Z_]\w*)\s*\(' for struct_name in structs],
      [rf'\bvoid\s+([a-zA-Z_]\w*)\s*\([^)]*inout\s+{struct_name}\s+\w+[^)]*\)' for struct_name in structs],
      [rf'\bvoid\s+([a-zA-Z_]\w*)\s*\([^)]*out\s+{struct_name}\s+\w+[^)]*\)' for struct_name in structs],
    ])
    return flatten_uniquely([re.findall(pattern, contents, re.IGNORECASE | re.DOTALL) for pattern in patterns])

  def detect_vertex_ep(contents):
    struct_patterns = [
      r'\bstruct\s+(\w+)\s*\{[^}]*SV_Position[^}]*\}',
      r'\bstruct\s+(\w+)\s*\{[^}]*:\s*POSITION[^}]*\}',
      r'\bstruct\s+(\w+)\s*\{[^}]*SV_VertexID[^}]*\}',
      r'\bstruct\s+(\w+)\s*\{[^}]*:\s*VERTEXID[^}]*\}',
      r'\bstruct\s+(\w+)\s*\{[^}]*SV_InstanceID[^}]*\}',
      r'\bstruct\s+(\w+)\s*\{[^}]*:\s*INSTANCEID[^}]*\}'
    ]
    structs = flatten_uniquely(
      [re.findall(struct_pattern, contents, re.IGNORECASE | re.DOTALL) for struct_pattern in struct_patterns]
    )
    patterns = flatten_uniquely([
      [rf'\b{struct_name}\s+([a-zA-Z_]\w*)\s*\(' for struct_name in structs],
      [rf'\bvoid\s+([a-zA-Z_]\w*)\s*\([^)]*inout\s+{struct_name}\s+\w+[^)]*\)' for struct_name in structs],
      [rf'\bvoid\s+([a-zA-Z_]\w*)\s*\([^)]*out\s+{struct_name}\s+\w+[^)]*\)' for struct_name in structs]
    ])
    return flatten_uniquely([re.findall(pattern, contents, re.IGNORECASE | re.DOTALL) for pattern in patterns])

  additional_searches = {
    'pixel' : detect_pixel_ep,
    'vertex' : detect_vertex_ep,
    'compute' : (lambda x : [])
  }

  failed_attempts = defaultdict(list)
  successfull_attempts = defaultdict(list)

  config.log.licenses.primary("Starting compilation parameters computation")
  for repo, file_jsons in walked:
    if not filter(repo.full_name):
      continue

    config.log.licenses.secondary(f"Computing compilation parameters for {repo.full_name}")

    repo_stats = load_repo_stats(config, repo)
    for file_json, _ in file_jsons:
      file_stat = file_stats(repo_stats, file_json)
      if file_stat['is_shader']:
        per_compiler_contents = {
          compiler_type: load_preprocessed_file(config, repo_stats, file_json, compiler_type)
          for compiler_type in CompilerTypes
        }
        normalised = _normalise(file_path(config, repo, file_json))

        default_if_absent(file_stat, 'entry_points', {})
        default_if_absent(file_stat, 'compilation_targets', {})
        for shader_type in selected_shader_types:
          file_stat['entry_points'][shader_type] = []
          file_stat['compilation_targets'][shader_type] = []

          if file_stat['shader_type'][shader_type] > 0:
            filename = file_name(file_json)
            file_stat['compilation_targets'][shader_type] = \
              flatten_uniquely([pattern.findall(filename) + pattern.findall(normalised)
                                for pattern in _comptarget_patterns[shader_type]])

            for compiler_type in CompilerTypes:
              contents = per_compiler_contents[compiler_type]
              if contents is not None:
                file_stat['entry_points'][shader_type] = \
                  flatten_uniquely(
                    [[match[0] for match in comp.findall(contents)] for comp in _entry_point_patterns[shader_type]] +
                    [additional_searches[shader_type](contents)] +
                    [file_stat['entry_points'][shader_type]]
                  )

            file_destination = successfull_attempts
            if len(file_stat['entry_points'][shader_type]) == 0:
              config.log.licenses.secondary(
                f"Unable to find {shader_type} entry point for {file_stat['case_sensitive_path']}")
              file_stat['entry_points'][shader_type] = _default_ep_values[shader_type]
              file_destination = failed_attempts
            else:
              config.log.licenses.secondary(
                f"Entry points for {file_stat['case_sensitive_path']} ({shader_type}):" +
                f" {file_stat['entry_points'][shader_type]}")
              file_destination = successfull_attempts
            file_destination[shader_type].append(file_stat['case_sensitive_path'])
            print(f"target {filename}: {file_stat['compilation_targets'][shader_type]}")

    _save_repo_stats(config, repo, repo_stats)

  for shader_type in _shader_types:
    config.log.licenses.primary(f"For {shader_type}: {len(successfull_attempts[shader_type])} successfully found,"
                                f" {len(failed_attempts[shader_type])} "
                                f"failed{'.' if len(failed_attempts[shader_type]) == 0 else ':'} ")
    for failure in failed_attempts[shader_type]:
      config.log.licenses.secondary(failure)

def file_has_stats_key(repo_stats, file_key):
  return file_key in repo_stats

def file_has_stats(repo_stats, file_json):
  return file_has_stats_key(repo_stats, _file_key(file_json))