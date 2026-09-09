import re

from src.config import Config
from enum import Enum

from src.analyse_file import load_repo_stats, file_stats
from src.utils import _shader_types, empty_dict_if_absent

import subprocess

from src.utils import CompilerTypes
class Compiler:
  def __init__(self, name : str, type : CompilerTypes, preprocessing_arr_gen, version_arr, compile_arr_gen):
    self.name = name
    self.type = type
    self._preprocessing_arr_gen = preprocessing_arr_gen
    self._version_arr = version_arr
    self._compile_arr_gen = compile_arr_gen

  def _execute(self, cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=1000)

  def _command(self, config : Config, suffix):
    return [config.compiler_path[self.type]] + suffix

  def _preprocessing_cmd(self, config : Config, input_path, output_path, additional):
    return self._command(config, self._preprocessing_arr_gen(output_path) + additional + [input_path])

  def _version_cmd(self, config : Config):
    return self._command(config, self._version_arr)

  def version(self, config : Config):
    result = self._execute(self._version_cmd(config))
    return result.stdout.splitlines()[0]

  def preprocess(self, config : Config, input_path, output_path, additional = []):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return self._execute(self._preprocessing_cmd(config, input_path, output_path, additional))

  def compile(self, config : Config, input_path, output_path, compilation_target : str, entry_point = None, additional = []):
    compilation_target = compilation_target.replace('x', '0')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return self._execute(self._command(config,
                                       self._compile_arr_gen(output_path, compilation_target, entry_point) +
                                       additional + [input_path]))

def new_compile_arr_gen(target_cmd, file_out_cmd, ep_command):
  return \
    lambda op, comptarget, ep : [target_cmd, comptarget, file_out_cmd, op] + ([] if ep is None else [ep_command, ep])


_compilers = {
  CompilerTypes.FXC : Compiler('fxc', CompilerTypes.FXC,
                               preprocessing_arr_gen = lambda op: ['/P', op],
                               version_arr = ['/?'],
                               compile_arr_gen=new_compile_arr_gen('/T', '/Fo', '/E')),
  CompilerTypes.DXC : Compiler('dxc', CompilerTypes.DXC,
                               preprocessing_arr_gen = lambda op: ['-P', op],
                               version_arr = ['--version'],
                               compile_arr_gen=new_compile_arr_gen('-T', '-Fo', '-E'))
}

from src.license_scanning import file_path

def _success(subprocess_result):
  return subprocess_result.returncode == 0

def preprocess(config : Config, walked, only_specified = False, only_missing = False):
  meta = load_prep_meta(config)

  versions = {
    CompilerTypes.FXC: _compilers[CompilerTypes.FXC].version(config),
    CompilerTypes.DXC: _compilers[CompilerTypes.DXC].version(config)
  }

  config.log.compile.primary(f"Starting preprocessing")
  config.log.compile.secondary(f"DXC version: {versions[CompilerTypes.DXC]}")
  config.log.compile.secondary(f"FXC version: {versions[CompilerTypes.FXC]}")


  for repo, file_jsons in walked:
    if only_specified and not any(
            len(_additional_directives(config, repo, CompStep.Preprocessing, compiler.type)) > 0
            for compiler in _compilers.values()):
      continue

    config.log.compile.secondary(f"Preprocessing files in {repo.full_name}")
    repo_stats = load_repo_stats(config, repo)

    for compiler in _compilers.values():
      add_directives = _additional_directives(config, repo, CompStep.Preprocessing, compiler.type)

      for file_json, _ in file_jsons:
        if only_missing and has_preprocessed_file(config, repo_stats, file_json, compiler.type):
          continue

        file_meta = empty_dict_if_absent(meta, file_stats(repo_stats, file_json)['hash'])
        empty_dict_if_absent(file_meta, 'versions')
        empty_dict_if_absent(file_meta, 'additional_directives')

        file_meta['versions'][compiler.name] = versions[compiler.type]

        if len(add_directives) > 0:
          file_meta['additional_directives'][compiler.name] = add_directives

        subprocess_result = compiler.preprocess(config, file_path(config, repo, file_json),
                              _preprocessed_file_path(config, repo_stats, file_json, compiler.type),
                              add_directives)

        file_meta[compiler.name] = _success(subprocess_result)
        if not _success(subprocess_result):
          config.log.compile.secondary(
            f"Failed to preprocess {file_stats(repo_stats, file_json)['case_sensitive_path']}" +
            f" with {compiler.name}: {subprocess_result.stderr}")
          empty_dict_if_absent(file_meta, 'errout')[compiler.name] = subprocess_result.stderr


    _save_prep_meta(config, meta)

class CompStep(Enum):
  Preprocessing = 0
  Compilation = 1

_comp_step_name = {
  CompStep.Preprocessing : 'preprocessing',
  CompStep.Compilation : 'compilation'
}

from src.utils import Repository
def _additional_directives(config : Config, repo : Repository, step : CompStep, compiler : CompilerTypes,
                           file_stat = None):
  def attempt_loading(step_name, item_name, compiler_name):
    if step_name in config.compile_directives \
            and item_name in config.compile_directives[step_name] \
            and compiler_name in config.compile_directives[step_name][item_name]:
      return config.compile_directives[step_name][repo.full_name][compiler_name]
    return None

  def default_if_none(value, default):
    return default if value is None else value

  step_name = _comp_step_name[step]
  repo_name = repo.full_name
  compiler_name = get_compiler_name(compiler)

  out = default_if_none(attempt_loading(step_name, repo_name, compiler_name),
                        default = attempt_loading(step_name, "__default__", compiler_name))
  if file_stat is not None:
    out = default_if_none(attempt_loading(step_name, file_stat['case_sensitive_path'], compiler_name), out)
  return default_if_none(out, [])



from src.utils import join_path
def _preprocessed_file_path(config : Config, repo_stats, file_json, compiler : CompilerTypes):
  return join_path(config.preprocessed_dir,
                   file_stats(repo_stats, file_json)['hash'] +
                   f"_{get_compiler_name(compiler)}")

# TODO: mb read meta first, but overall same thing
def load_preprocessed_file(config : Config, repo_stats, file_json, compiler : CompilerTypes):
  try:
    with open(_preprocessed_file_path(config, repo_stats, file_json, compiler), 'r', encoding='utf-8') as f:
      content = f.read()
    return content
  except Exception as e:
    return None

import os
def has_preprocessed_file(config : Config, repo_stats, file_json, compiler : CompilerTypes):
  return os.path.isfile(_preprocessed_file_path(config, repo_stats, file_json, compiler))

def _preprocessed_meta_path(config : Config):
  return join_path(config.preprocessed_dir, 'meta.json')

import json
def load_prep_meta(config : Config):
  try:
    with open(_preprocessed_meta_path(config), "r") as f:
      return json.load(f)
  except Exception as e:
    config.log.licenses.primary(f"Unable to load preprocessed meta data, returning empty")
    return {}

def _save_prep_meta(config : Config, meta):
  path = _preprocessed_meta_path(config)
  path.parent.mkdir(parents=True, exist_ok=True)
  with open(path, "w") as f:
    json.dump(meta, f)

def get_compiler_name(compiler : CompilerTypes):
  return _compilers[compiler].name

def _compiler_type_from_target(comptarget : str) -> CompilerTypes:
  if int(comptarget.split('_')[1]) > 5:
    return CompilerTypes.DXC
  return CompilerTypes.FXC

class ProfileTypes(Enum):
  Pixel = "ps"
  Vertex = "vs"
  Compute = "cs"
  Library = "lib"

_profile_types = {
  "pixel": ProfileTypes.Pixel,
  "vertex": ProfileTypes.Vertex,
  "compute": ProfileTypes.Compute,
  "library": ProfileTypes.Library
}

# TODO: Move to config json
_comptarget_versions = {
  ProfileTypes.Pixel : {
    2 : [0],
    3 : [0],
    4 : [0, 1],
    5 : [0, 1],
    6 : [0, 3, 6]
  },
  ProfileTypes.Vertex : {
    2: [0],
    3: [0],
    4: [0, 1],
    5: [0, 1],
    6: [0, 3, 6]
  },
  ProfileTypes.Compute : {
    4: [0, 1],
    5: [0, 1],
    6: [0, 3, 6]
  },
  ProfileTypes.Library : {
    4: [0, 1],
    5: [0],
    6: [0, 3, 6]
  }
}

_hv_variants = ['2016', '2018', '2021']

_comptarget_full_list = {
  profile_type: [f"{profile_type.value}_{version}_{subversion}"
                 for version, subversions in _comptarget_versions[profile_type].items()
                 for subversion in subversions
                 ]
  for profile_type in ProfileTypes
}

def _compiled_file_path(config : Config, repo_stats, file_json, comptarged, entry_point = None, spirv = False):
  return join_path(config.compiled_dir,
            file_stats(repo_stats, file_json)['hash'] +
            f"_{comptarged}_{'' if entry_point is None else entry_point}{'_spirv.spv' if spirv else ''}")

def _has_compiled_file(config : Config, repo_stats, file_json, comptarged, entry_point = None, spirv = False):
  return os.path.isfile(_compiled_file_path(config, repo_stats, file_json, comptarged, entry_point, spirv))

def _compile_meta_path(config : Config):
  return join_path(config.compiled_dir, 'meta.json')

def compile(config : Config, walked, skip_successful = False):
  config.log.compile.primary("Starting file compilation")
  meta = load_compile_meta(config)

  def handle_shader_type(shader_type, file_stat, file_json, repo, repo_meta, dxc_additionals = [],
                         skip_non_dxc = False):
    file_profile_meta = empty_dict_if_absent(empty_dict_if_absent(repo_meta, file_stat['hash']), shader_type)

    profile = _profile_types[shader_type]
    comptargets = \
      file_stat['compilation_targets'][shader_type] if shader_type in file_stat['compilation_targets'] else []
    if len(comptargets) == 0:
      comptargets = _comptarget_full_list[profile]

    failures = empty_dict_if_absent(file_profile_meta, 'failures')
    successes = empty_dict_if_absent(file_profile_meta, 'successes')

    for comptarget in comptargets:
      for entry_point in \
              (file_stat['entry_points'][shader_type] if shader_type in file_stat['entry_points'] else [None]):
        if entry_point in successes:
          continue

        compiler = _compilers[_compiler_type_from_target(comptarget)]

        if skip_non_dxc and compiler.type != CompilerTypes.DXC:
          continue

        additionals = _additional_directives(config, repo, CompStep.Compilation, compiler.type, file_stat) + \
          (dxc_additionals if compiler.type == CompilerTypes.DXC else [])
        subprocess_result = compiler.compile(
          config,
          _preprocessed_file_path(config, repo_stats, file_json, compiler.type),
          _compiled_file_path(config, repo_stats, file_json, comptarget, entry_point, spirv=False),
          comptarget,
          entry_point,
          additionals
        )
        if subprocess_result.returncode != 0:
          empty_dict_if_absent(failures, entry_point)[comptarget] = \
            (subprocess_result.stderr, compiler.name, additionals)
        else:
          config.log.compile.secondary(f"Success: {file_stat['case_sensitive_path']} {entry_point} {comptarget}")
          spirv_data = None
          if compiler.type == CompilerTypes.DXC and shader_type != 'library':
            target_enviroments = ['vulkan1.0', 'vulkan1.1', 'vulkan1.2', 'vulkan1.3']
            layouts = [None, '-fvk-use-dx-layout', '-fvk-use-gl-layout']
            spirv_errors = []
            for target_env in target_enviroments:
              for layout in layouts:
                spirv_additionals = ['-spirv', f'-fspv-target-env={target_env}'] +\
                                    ([layout] if layout is not None else [])
                spirv_result = compiler.compile(
                  config,
                  _preprocessed_file_path(config, repo_stats, file_json, compiler.type),
                  _compiled_file_path(config, repo_stats, file_json, comptarget, entry_point, spirv=True),
                  comptarget,
                  entry_point,
                  additionals + spirv_additionals
                )
                if spirv_result.returncode == 0:
                  spirv_data = (True, spirv_additionals)
                  break
                else:
                  spirv_errors.append((spirv_additionals, spirv_result.stderr))
              if spirv_data is not None:
                break

            if spirv_data is None:
              config.log.compile.secondary(f"! But failed spirv: {spirv_errors}")
              spirv_data = (False, spirv_errors)
            else:
              config.log.compile.secondary(f"Spirv generated also, env={spirv_data[1]}")
          successes[entry_point] = (comptarget, compiler.name, additionals, spirv_data)

    return len(successes) > 0

  def iterate_over_hv(shader_type, file_stat, file_json, repo, repo_meta):
    for hv_variant in _hv_variants:
      # Try all language versions for dxc, but run fxc only on the first one
      if handle_shader_type(shader_type, file_stat, file_json, repo, repo_meta,
                            dxc_additionals=['-HV', hv_variant], skip_non_dxc=(hv_variant == _hv_variants[0])):
        break

  for repo, file_jsons in walked:
    config.log.compile.primary(f"Starting file compilations for {repo.full_name}")
    repo_stats = load_repo_stats(config, repo)
    repo_meta = empty_dict_if_absent(meta, repo.full_name)

    for file_json, _ in file_jsons:
      file_stat = file_stats(repo_stats, file_json)
      file_meta = empty_dict_if_absent(repo_meta, file_stat['hash'])
      if skip_successful and any(profile_type in file_meta and
                                 len(file_meta[profile_type]['successes']) > 0 for profile_type in _profile_types.keys()):
        continue

      for shader_type in _shader_types:
        if file_stat['shader_type'][shader_type] > 0:
          file_meta[shader_type] = {} # if don't want to redo just pick skip_successfull = True
          iterate_over_hv(shader_type, file_stat, file_json, repo, repo_meta)



      if not any(shader_type in file_meta and
                 len(file_meta[shader_type]['successes']) > 0 for shader_type in _shader_types):
        iterate_over_hv('library', file_stat, file_json, repo, repo_meta)
        if len(file_meta['library']['successes']) == 0:
          config.log.compile.secondary(f"! Zero successful compilations for {file_stat['case_sensitive_path']}")
          for profile_type, eps in file_meta.items():
            config.log.compile.secondary(f"{profile_type}: ")
            for failed_ep, attempts in eps['failures'].items():
              config.log.compile.secondary(f"-- {failed_ep}: ")
              for attempted_target, result in attempts.items():
                config.log.compile.secondary(f"-- -- {attempted_target}: {result[0]}")
    _save_compile_meta(config, meta)




# TODO: fix copypaste
def load_compile_meta(config : Config):
  try:
    with open(_compile_meta_path(config), "r") as f:
      return json.load(f)
  except Exception as e:
    config.log.licenses.primary(f"Unable to load compile meta data, returning empty")
    return {}

def _save_compile_meta(config : Config, meta):
  path = _compile_meta_path(config)
  path.parent.mkdir(parents=True, exist_ok=True)
  with open(path, "w") as f:
    json.dump(meta, f)

# TODO: fix copypaste
def _decompile_meta_path(config : Config):
  return join_path(config.decompiled_dir, "meta.json")

def load_decompile_meta(config : Config):
  try:
    with open(_decompile_meta_path(config), "r") as f:
      return json.load(f)
  except Exception as e:
    config.log.licenses.primary(f"Unable to load decompile meta data, returning empty")
    return {}

def _save_decompile_meta(config : Config, meta):
  path = _decompile_meta_path(config)
  path.parent.mkdir(parents=True, exist_ok=True)
  with open(path, "w") as f:
    json.dump(meta, f)

from src.utils import major_shader_model
def _directx_version(comptarget: str) -> int:
  split = comptarget.split('_')
  major = major_shader_model(comptarget)
  minor = split[2]
  if major <= 3:
    return 9
  elif major == 4:
    return 10
  elif major == 5:
    if minor in ['x', '0']:
      return 11
    else:
      return 12
  else:
    return 12


from src.utils import _shader_types_ext, Decompilers
_decompilers_to_system = {
  Decompilers.RGA : 'amd',
  Decompilers.ISA : 'intel'
}


def _map_shader_type_for_rga_vk_offline(comptarget : str):
  mapping = [('ps', 'frag'), ('cs', 'comp'), ('vs', 'vert')]
  return next((mapped for key, mapped in mapping if comptarget.startswith(key)), None)

def isa_dir(config: Config, file_stat, system, entry_point, comptarget):
  return join_path(config.decompiled_dir, file_stat['hash']) / system / f"{comptarget}_{entry_point}"

def isa_path(config: Config, file_stat, system, entry_point, comptarget, arch_name):
  suffix = ""
  if system == 'amd':
    if _directx_version(comptarget) >= 12:
      suffix = f"_isa_{_map_shader_type_for_rga_vk_offline(comptarget)}"
    suffix += ".amdisa"
  else:
    suffix = f".asm"
  return isa_dir(config, file_stat, system, entry_point, comptarget) / (arch_name + suffix)


def decompile(config: Config, walked, decompilators = None, skip_successful = False):
  config.log.compile.primary("Starting decompilation")
  save_every_x = 100

  if decompilators is None:
    decompilators = [Decompilers(decomp_name) for decomp_name in config.isa_devices.keys()]
  else:
    for decomp in decompilators:
      if decomp.value not in config.decompilator_paths:
        config.log.compile.primary(f"Executable path not provided for {decomp.value}. Aborting")
        return


  def get_decompile_additionals(decompilator : Decompilers, mode = None):
    if mode:
      return config.decompile_directives.get(decompilator.value, {}).get(mode, [])
    return config.decompile_directives.get(decompilator.value, [])

  def parse_successes_rga(output : str):
    successes = []
    for line in output.split('\n'):
      match = re.match(r'Building for (\w+)\.\.\. succeeded\.', line)
      if match:
        successes.append(match.group(1))
    return successes

  out_meta = load_decompile_meta(config)
  compiled_meta = load_compile_meta(config)

  files_decompiled = 0
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
              file_out_meta = empty_dict_if_absent(out_meta, file_stat['hash'])
              st_out_meta = empty_dict_if_absent(file_out_meta, shader_type)

              for entry_point, info in file_comp_meta[shader_type]['successes'].items():
                ep_out_meta = empty_dict_if_absent(st_out_meta, entry_point)
                out_meta_attempts = ep_out_meta.setdefault('attempts', [])
                out_meta_successes_ep = empty_dict_if_absent(ep_out_meta, 'successes')

                comptarget, compiler_name, _, spirv_info = info
                dx_version = _directx_version(comptarget)
                if dx_version <= 9:
                  out_meta_attempts.append(("", comptarget, [], "Precheck: Unsupported shader model."))
                  continue # Shader models 3.0 and below require second or third tools for each platform,
                  # And don't see much value in them, so didn't add.

                for decomp in decompilators:
                  system = _decompilers_to_system[decomp]
                  out_meta_successes = empty_dict_if_absent(out_meta_successes_ep, system)
                  decomp_name = decomp.value

                  if skip_successful and len(out_meta_successes) > 0:
                    config.log.compile.secondary(f"Skip successful on, skipping {decomp_name} for "
                                                 f"{file_stat['case_sensitive_path']} {entry_point} {comptarget}")
                    continue

                  config.log.compile.secondary(f"Decompiling {file_stat['case_sensitive_path']}"
                                               f" {entry_point} {comptarget} with {decomp_name}")


                  command = []
                  additionals = []
                  output_dir = isa_dir(config, file_stat, system, entry_point, comptarget)


                  spirv = False
                  if decomp == Decompilers.RGA:
                    source = 'dx11' if dx_version <= 11 else 'vk-spv-offline'

                    command = ['-s', source]
                    devices = config.isa_devices.get(decomp_name, {}).get(source, [])
                    if len(devices) > 0:
                      command += ['-c', ','.join(devices)]

                    command += ['--isa', str(output_dir) + '/']

                    if source == 'dx11':
                      command += ['--dxbc']
                    else:
                      command += [f'--{_map_shader_type_for_rga_vk_offline(comptarget)}']
                      spirv = True

                    additionals = get_decompile_additionals(decomp, source)
                  elif decomp == Decompilers.ISA:
                    if major_shader_model(comptarget) >= 6:
                      config.log.compile.secondary("Skipping, shader model higher than 5.1")
                      continue # IntelShaderAnalyzer works up to 5.1

                    api = 'dx11' if dx_version <= 11 else 'dx12'
                    command = ['--api', api, '-s', 'dxbc']

                    devices = config.isa_devices.get(decomp_name, {}).get(api, [])
                    if len(devices) > 0:
                      for device in devices:
                        command += ['-c', device]

                    command += ['--isa', str(output_dir) + '/']
                    spirv = False

                  if spirv and (spirv_info is None or not spirv_info[0]):
                    config.log.compile.secondary("Failed: missing required spir-v compiled file")
                    out_meta_attempts.append((decomp_name, comptarget,
                                              [], "Precheck: missing required spir-v compiled file"))
                    continue
                  command += [_compiled_file_path(config, repo_stats, file_json, comptarget,
                                                  entry_point, spirv=spirv)]

                  output_dir.mkdir(parents=True, exist_ok=True)
                  decomp_result = subprocess.run(
                    [config.decompilator_paths[decomp_name]] +
                    additionals +
                    command,
                    capture_output = True, text = True, timeout = 1000
                  )

                  if decomp_result.returncode == 1:
                    config.log.compile.secondary(f"Process failed ({decomp_result.returncode}): "
                                                 f"{decomp_result.stdout} stderr: {decomp_result.stderr}")
                    out_meta_attempts.append((decomp_name,
                                              comptarget, [], f"Process failed:\n stdout: {decomp_result.stdout} \n"
                                                             f" stderr: {decomp_result.stderr}"))
                    continue

                  decomp_successes = []

                  if decomp == Decompilers.RGA:
                    decomp_successes = parse_successes_rga(decomp_result.stdout)
                  elif decomp == Decompilers.ISA:
                    decomp_successes = [f.stem for f in output_dir.glob("*.asm")] # No output, so just guessing.
                    # Obviously, can verify against previously present files/ update times to check what was
                    # actually generated, but won't for now.

                  if len(decomp_successes) == 0:
                    config.log.compile.secondary(f"! Zero successful decompilaions.")
                    config.log.compile.secondary(decomp_result.stdout)
                  else:
                    config.log.compile.secondary(f"Successfully decompiled for:")
                    for succ in decomp_successes:
                      out_meta_successes[succ] = (comptarget, additionals)
                      config.log.compile.secondary(f" {succ}")
                  out_meta_attempts.append((decomp_name, comptarget, [], decomp_result.stdout))

                  files_decompiled += 1
                  if files_decompiled % save_every_x == 0:
                    config.log.compile.primary(f"Saving, attempted {files_decompiled}")
                    _save_decompile_meta(config, out_meta)

      _save_decompile_meta(config, out_meta)

import tempfile
import shutil
def remove_line_directives(config : Config, walked):
  config.log.compile.primary(f"Starting line directives removal")

  for repo, file_jsons in walked:
    config.log.compile.secondary(f"Processing files in {repo.full_name}")
    repo_stats = load_repo_stats(config, repo)

    for compiler in _compilers.values():
      for file_json, _ in file_jsons:
        path = _preprocessed_file_path(config, repo_stats, file_json, compiler.type)
        try:
          with open(path, 'r') as f, tempfile.NamedTemporaryFile('w', delete=False) as tmp:
            for line in f:
              if not line.startswith('#line'):
                tmp.write(line)
          shutil.move(tmp.name, path)
        except Exception as e:
          config.log.compile.secondary(f"Failed on {file_json['path']} {compiler.name} : {e}")

