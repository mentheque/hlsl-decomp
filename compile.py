from config import Config
from enum import Enum

from analyse_file import load_repo_stats, file_stats

import subprocess

from utils import CompilerTypes
class Compiler:
  def __init__(self, name : str, type : CompilerTypes, preprocessing_arr_gen, version_arr):
    self.name = name
    self.type = type
    self._preprocessing_arr_gen = preprocessing_arr_gen
    self._version_arr = version_arr

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



_compilers = {
  CompilerTypes.FXC : Compiler('fxc', CompilerTypes.FXC,
                               preprocessing_arr_gen = lambda op: ['/P', op],
                               version_arr = ['/?']),
  CompilerTypes.DXC : Compiler('dxc', CompilerTypes.DXC,
                               preprocessing_arr_gen = lambda op: ['-P', op],
                               version_arr = ['--version'])
}

from license_scanning import file_path

def _success(subprocess_result):
  return subprocess_result.returncode == 0

def preprocess(config : Config, walked, only_specified = False):
  def empty_dict_if_absent(dictionary, key):
    if key not in dictionary:
      dictionary[key] = {}
    return dictionary[key]

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
          empty_dict_if_absent(file_meta, 'errout')[compiler.name] = subprocess_result.stderr


    _save_prep_meta(config, meta)

class CompStep(Enum):
  Preprocessing = 0
  Compilation = 1

_comp_step_name = {
  CompStep.Preprocessing : 'preprocessing',
  CompStep.Compilation : 'compilation'
}

from utils import Repository
def _additional_directives(config : Config, repo : Repository, step : CompStep, compiler : CompilerTypes):
  step_name = _comp_step_name[step]
  repo_name = repo.full_name
  compiler_name = get_compiler_name(compiler)
  if step_name in config.compile_directives \
    and repo_name in config.compile_directives[step_name] \
    and compiler_name in config.compile_directives[step_name][repo_name]:
    return config.compile_directives[step_name][repo.full_name][compiler_name]

  return []



from utils import join_path
def _preprocessed_file_path(config : Config, repo_stats, file_json, compiler : CompilerTypes):
  return join_path(config.preprocessed_dir,
                   file_stats(repo_stats, file_json)['hash'] +
                   f"_{get_compiler_name(compiler)}")

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