from config import Config

from analyse_file import file_stats, load_repo_stats, file_has_stats
from utils import CompilerTypes

class BaseStat:
  def __init__(self):
    self._is_shader = 0
    self._preprocessed_dxc = 0
    self._preprocessed_fxc = 0
    self._preprocessed_either = 0
    self._compiled = 0

  def merge(self, other : 'BaseStat'):
    self._is_shader += other._is_shader
    self._preprocessed_dxc += other._preprocessed_dxc
    self._preprocessed_fxc += other._preprocessed_fxc
    self._preprocessed_either += other._preprocessed_either
    self._compiled += other._compiled

  def add_file(self, preprocessed_by : list, compiled : bool):
    self._is_shader+=1
    if len(preprocessed_by) > 0:
      self._preprocessed_either += 1

    for preprocessor in preprocessed_by:
      if preprocessor == CompilerTypes.DXC:
        self._preprocessed_dxc+= 1
      elif preprocessor == CompilerTypes.FXC:
        self._preprocessed_fxc += 1

    if compiled:
      self._compiled += 1

  def compiled_rate(self):
    return self._compiled / self._is_shader

  def compiled_over_preprocessed_rate(self):
    return self._compiled / self._preprocessed_either


from utils import _shader_types, _shader_types_ext
class TypedStats:
  def __init__(self):
    self._base = BaseStat()
    self._typed = {
      shader_type : BaseStat()
      for shader_type in _shader_types_ext
    }

  def add_file(self, preprocessed_by : list, types_predicted, types_compiled):
    self._base.add_file(preprocessed_by, any(types_compiled[shader_type] for shader_type in _shader_types_ext))
    for shader_type in _shader_types_ext:
      if shader_type not in types_predicted or types_predicted[shader_type] > 0:
        if types_compiled[shader_type]:
          self._typed[shader_type].add_file(preprocessed_by, True)
        else:
          self._typed[shader_type].add_file(preprocessed_by, False)

  def merge(self, other : 'TypedStats'):
    self._base.merge(other._base)
    for shader_type in _shader_types_ext:
      self._typed[shader_type].merge(other._typed[shader_type])

from compile import load_compile_meta, has_preprocessed_file, _directx_version
from utils import join_path
from collections import defaultdict
def compilation_stats(config : Config, walked, list_uncompiled_files = False):
  uncompiled = {
    shader_type : []
    for shader_type in _shader_types
  }

  dx_versions = defaultdict(int)

  total_dxc_non_lib = 0
  total_compiled_to_spirv = 0

  total_out = TypedStats()
  repo_outs = []
  meta = load_compile_meta(config)
  for repo, file_jsons in walked:
    repo_out = TypedStats()
    repo_stats = load_repo_stats(config, repo)
    repo_meta = meta[repo.full_name]
    for file_json, _ in file_jsons:
      file_stat = file_stats(repo_stats, file_json)
      preprocessed_by = []
      compiled_types = {
        shader_type : False
        for shader_type in _shader_types_ext
      }

      for compiler_type in CompilerTypes:
        if has_preprocessed_file(config, repo_stats, file_json, compiler_type):
          preprocessed_by.append(compiler_type)

      if file_stat['hash'] in repo_meta:
        file_meta = repo_meta[file_stat['hash']]
        for shader_type in _shader_types_ext:
          if shader_type in file_meta and len(file_meta[shader_type]['successes']) > 0:
            compiled_types[shader_type] = True
            for entry_point, data in file_meta[shader_type]['successes'].items():
              dx_versions[_directx_version(data[0])] += 1

              if len(data) == 4 and data[3] is not None:
                total_dxc_non_lib += 1
                if data[3][0]:
                  total_compiled_to_spirv += 1

          elif shader_type in _shader_types and file_stat['shader_type'][shader_type] > 0:
            uncompiled[shader_type].append((repo.full_name, file_stat['case_sensitive_path']))
        repo_out.add_file(preprocessed_by,
                          file_stat['shader_type'],
                          compiled_types)

    total_out.merge(repo_out)
    repo_outs.append((repo, repo_out))

  sorted_list = sorted(
    repo_outs,
    key=lambda x: (x[1]._base.compiled_rate(), x[1]._base._is_shader)
  )

  print(f"Compiled rate : {total_out._base.compiled_rate()} out of {total_out._base._is_shader} files")
  print(f"For eligible successfully compiled files spirv success rate: {total_compiled_to_spirv/total_dxc_non_lib}")
  for shader_type in _shader_types:
    print(f"{shader_type} : {total_out._typed[shader_type].compiled_rate()}"
          f" out of {total_out._typed[shader_type]._is_shader} files. "
          f"{total_out._typed[shader_type].compiled_over_preprocessed_rate()} over preprocessed.")
  print("For successful compilations, dx versions are: ")
  for dxv, counter in dx_versions.items():
    print(f"{dxv} : {counter}")


  print("--------------- Repo stats -------------")
  under_5p = 0
  for repo, repo_out in sorted_list:
    print(f"{repo.full_name}: {repo_out._base.compiled_rate()} out of {repo_out._base._is_shader} files")
    if repo_out._base.compiled_rate() < 0.05:
      under_5p += repo_out._base._is_shader - repo_out._base._compiled

  import csv

  # Create and write CSV
  with open(join_path(config.exported_zip_dir, 'repos_compiled.csv'), 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    for repo, repo_out in sorted_list:
      writer.writerow(
        [repo.full_name, repo_out._base._compiled, repo_out._base._is_shader, repo_out._base.compiled_rate()])

  print(f"Out of that, {under_5p} of uncompiled files are in repos with rate under 5%")

  if list_uncompiled_files:
    for shader_type in _shader_types:
      print(f"---- Uncompiled {shader_type} shaders ----")
      for repo_name, file_path in uncompiled[shader_type]:
        print(f"{repo_name} {file_path}")

from compile import load_decompile_meta, _decompilers_to_platform
from utils import empty_dict_if_absent, Decompilers
def decompilation_stats(config : Config, walked):
  platforms = set(_decompilers_to_platform.values())

  meta = load_decompile_meta(config)
  compiled_meta = load_compile_meta(config)

  successful_sources_by_platform = {}
  total_produced_by_platform = {}
  for platform in platforms:
    successful_sources_by_platform[platform] = 0
    total_produced_by_platform[platform] = 0

  sources_by_shader_model = {}

  for repo, file_jsons in walked:
    if repo.full_name in compiled_meta:
      compiled_meta_repo = compiled_meta[repo.full_name]
      repo_stats = load_repo_stats(config, repo)
      for file_json, _ in file_jsons:
        file_stat = file_stats(repo_stats, file_json)
        if file_stat['hash'] in compiled_meta_repo:
          file_comp_meta = compiled_meta_repo[file_stat['hash']]

          # Not trying lib_x_x, because no way to properly decompile
          for shader_type in _shader_types:
            if shader_type in file_comp_meta:
              file_out_meta = empty_dict_if_absent(meta, file_stat['hash'])
              st_out_meta = empty_dict_if_absent(file_out_meta, shader_type)

              for entry_point, info in file_comp_meta[shader_type]['successes'].items():
                ep_out_meta = empty_dict_if_absent(st_out_meta, entry_point)
                out_meta_successes_ep = empty_dict_if_absent(ep_out_meta, 'successes')

                comptarget, compiler_name, _, spirv_info = info
                if comptarget.startswith("lib"):
                  continue
                sources_by_shader_model.setdefault(comptarget[3:], 0)
                sources_by_shader_model[comptarget[3:]] += 1

                dx_version = _directx_version(comptarget)
                if dx_version <= 9:
                  continue # Shader models 3.0 and below require second or third tools for each platform,
                  # And don't see much value in them, so didn't add.

                for platform in platforms:
                  out_meta_successes = empty_dict_if_absent(out_meta_successes_ep, platform)
                  if len(out_meta_successes) > 0:
                    successful_sources_by_platform[platform] += 1
                    total_produced_by_platform[platform] += len(out_meta_successes)

  print(f"Total non-library compiled: {sum(sources_by_shader_model.values())}")
  print(f"From that, by shader model:")
  amd_legible = 0
  intel_legible = 0
  for shmodel, count in sorted(sources_by_shader_model.items()):
    print(f"{shmodel}: {count}")
    major = int(shmodel[0])
    if major <= 3 or shmodel == "5_1":
      continue
    elif major >= 6:
      amd_legible += count
    else:
      amd_legible += count
      intel_legible += count
  print(f"Therefore, {amd_legible} files legible for amd decompilation, {intel_legible} for intel")
  print(f"Success rate: amd - {successful_sources_by_platform['amd']/amd_legible}, "
        f"intel - {successful_sources_by_platform['intel']/intel_legible}")
  print(f"Total isa produced:")
  for platform in platforms:
    print(f"{platform} - {total_produced_by_platform[platform]}")
