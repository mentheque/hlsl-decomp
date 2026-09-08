from config import Config, LicenseGroup
from utils import Repository
from collections import OrderedDict


from license_scanning import _filter_file_conclusive, _sort_file_conclusive
from analyse_file import load_repo_stats, _file_key, file_stats, file_has_stats
from git_utils import repo_commit_sha

class BaseExportInputs:
  def __init__(self, config, file_stat, commit_sha, repo : Repository, license_jsons, repo_stats):
    self.config = config
    self.file_stat = file_stat
    self.commit_sha = commit_sha
    self.repo = repo
    self.license_jsons = license_jsons
    self.repo_stats = repo_stats

def _new_get_stat(key1, key2 = None, transform = (lambda x : x)):
  return (lambda be_inputs:
          transform(be_inputs.file_stat[key1] if key2 is None else be_inputs.file_stat[key1][key2]))

from utils import reponameless_path

def _get_link_inner(path, commit_sha, repo):
  return f"https://github.com/{repo.full_name}/blob/{commit_sha}/{reponameless_path(path)}"
def _get_link(be_inputs):
  return _get_link_inner(be_inputs.file_stat['case_sensitive_path'], be_inputs.commit_sha, be_inputs.repo)

def _get_license_link(be_inputs):
  if isinstance(be_inputs.license_jsons, list):
    if len(be_inputs.license_jsons) == 0:
      return ""
    elif len(be_inputs.license_jsons) > 1:
      return "Inconclusive"
    else:
      return _get_link_inner(be_inputs.license_jsons[0]['path'], be_inputs.commit_sha, be_inputs.repo)
  else:
    return _get_link_inner(be_inputs.license_jsons['path'], be_inputs.commit_sha, be_inputs.repo)

def _get_author(be_inputs):
  return be_inputs.repo.full_name.split('/')[0]

def _get_repo_name(be_inputs):
  return be_inputs.repo.full_name

_license_mapping = {
  LicenseGroup.GPL : 'GPL',
  LicenseGroup.Permissive : 'Permissive',
  LicenseGroup.Other : 'Other',
  LicenseGroup.ExternalFile : 'ExternalFile',
  LicenseGroup.Unidentified : 'Unidentified',
  LicenseGroup.Inconclusive : 'Inconclusive',
  LicenseGroup.NoIncludes : 'No includes'
}

from repository_lists import RepositoryLists
_list_name_mapping = {
  RepositoryLists.Full: "Full",
  RepositoryLists.SelectedLicenses: "SelectedLicenses",
  RepositoryLists.TopStarred : "TopStarred"
}


def _new_map_include_to_stat(key, transform_if_not_present = (lambda inc : '')):
  def inner(be_inputs):
    return ','.join([be_inputs.repo_stats[include][key] if include in be_inputs.repo_stats
                     else transform_if_not_present(include)
                     for include in be_inputs.file_stat['includes']])
  return inner


def _license_prefix(config : Config, file_stat, license_jsons):
  if not isinstance(license_jsons, list) and license_jsons["detected_license_expression_spdx"] is not None \
          and file_stat['license'] in [LicenseGroup.GPL, LicenseGroup.Permissive]:
    for license in config.licenses:
      if license_jsons["detected_license_expression_spdx"].startswith(license.unique_prefix):
        return license.unique_prefix

  return '_other_'

def _get_license_prefix(be_inputs):
  return _license_prefix(be_inputs.config, be_inputs.file_stat, be_inputs.license_jsons)

from analyse_file import _platforms, _shader_types
# hash, repo_path, is_shader, link, author, repo_name, size, lines, platform, type, license, license_source_link,
# includes, includes_hash, includes_worst_case_licenses.
_csv_structure_base = OrderedDict([
  ('hash', _new_get_stat('hash')),
  ('repo_path', _new_get_stat('case_sensitive_path')),
  ('is_shader', _new_get_stat('is_shader')),
  ('link', _get_link),
  ('author', _get_author),
  ('repo', _get_repo_name),
  ('size (bytes)', _new_get_stat('size')),
  ('lines', _new_get_stat('lines')),
] +
                                  [
  (f'platform_{platform_name}', _new_get_stat('platforms', platform_name)) for platform_name in _platforms
] +
                                  [
  (f'shader_type_{shader_type}', _new_get_stat('shader_type', shader_type)) for shader_type in _shader_types
] +
                                  [
  ('license', _new_get_stat('license', transform=_license_mapping.get)),
  ('license_source_link', _get_license_link),
  ('includes', _new_map_include_to_stat('case_sensitive_path', transform_if_not_present = (lambda x: x))),
  ('includes_hash', _new_map_include_to_stat('hash')),
  ('worst_included_license', _new_get_stat('worst_included_license', transform=_license_mapping.get)),
  ('archive_location', _get_license_prefix),
  ('compiled', _new_get_stat('compiled')),
])

import zipfile
from io import StringIO
import csv
from license_scanning import file_path

from utils import join_path
def export_file_path(config : Config, rlist_variant: RepositoryLists, name):
  def empty_if_none(value, transform = (lambda x : x)):
    return '' if value is None else transform(value)

  return join_path(config.exported_zip_dir,
                   f'export_{empty_if_none(rlist_variant, _list_name_mapping.get)}_{empty_if_none(name)}.zip')

def export_base(config : Config, walked, rlist_variant: RepositoryLists = None, name = None):
  config.log.export.primary("Starting export process for base task")
  output = StringIO()
  writer = csv.writer(output)
  writer.writerow(_csv_structure_base.keys())
  files = []
  for repo, file_jsons in walked:
    repo_stats = load_repo_stats(config, repo)
    commit_sha = repo_commit_sha(config, repo)
    for file_json, license_sources in file_jsons:
      if file_has_stats(repo_stats, file_json):
        file_stat = file_stats(repo_stats, file_json)
        writer.writerow([func(BaseExportInputs(config, file_stat, commit_sha, repo, license_sources, repo_stats))
                         for func in _csv_structure_base.values()])

        files.append((file_path(config, repo, file_json),
                      _license_prefix(config, file_stat, license_sources) + '/' + file_stat['hash']))


  config.log.export.primary("Contents calculated, writing zip file")
  try:
    export_path = export_file_path(config, rlist_variant, name)
    export_path.parent.mkdir(exist_ok=True, parents=True)
    with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
      zipf.writestr('stats.csv', output.getvalue())
      for file, new_name in files:
        zipf.write(file, new_name)
  except Exception as e:
    config.log.export.primary(f"Failed to write zip file: {e}")
    raise e

class IsaExportInputs:
  def __init__(self, config, file_stat, commit_sha, repo : Repository, license_jsons, repo_stats, successes,
               compilation_details):
    self.config = config
    self.file_stat = file_stat
    self.commit_sha = commit_sha
    self.repo = repo
    self.license_jsons = license_jsons
    self.repo_stats = repo_stats
    self.successes = successes
    self.compilation_details = compilation_details

def _new_get_comp_detail(key : str):
  return lambda isa_inputs: isa_inputs.compilation_details[key]
def _new_get_succ_listed(system : str):
  return lambda isa_inputs : ','.join(isa_inputs.successes.setdefault(system, {}).keys())
def _new_get_succ_number(system : str):
  def inner(isa_inputs : IsaExportInputs):
    if system not in isa_inputs.successes:
      return 0
    return len(isa_inputs.successes[system])
  return inner

from utils import major_shader_model
def _archive_source_path(file_stat, comptarget : str):
  return 'sources/' + file_stat['hash'] + '_' + ('fxc' if major_shader_model(comptarget) <= 5 else 'dxc')

def _get_archive_source_path(isa_inputs : IsaExportInputs):
  return _archive_source_path(isa_inputs.file_stat, isa_inputs.compilation_details['compilation_target'])

def _archive_isa_dir(file_stat, comptarget: str, entry_point : str):
  return f"isa/{file_stat['hash']}_{entry_point}_{comptarget}/"

def _get_archive_isa_dir(isa_inputs : IsaExportInputs):
  return _archive_isa_dir(isa_inputs.file_stat,
                          isa_inputs.compilation_details['compilation_target'],
                          isa_inputs.compilation_details['entry_point'])

_csv_structure_isa = OrderedDict([
  ('hash', _new_get_stat('hash')),
  ('shader_type', _new_get_comp_detail('shader_type')),
  ('entry_point', _new_get_comp_detail('entry_point')),
  ('compilation_target', _new_get_comp_detail('compilation_target')),
  ('combined_license',
   lambda isa_inputs:
   _license_mapping.get(max(isa_inputs.file_stat['worst_included_license'], isa_inputs.file_stat['license'])))] +
  [item for sublist in [
    [
      (f'{system}_decompiled', _new_get_succ_number(system)),
      (f'{system}_archs', _new_get_succ_listed(system))
    ] for system in ['amd', 'intel']
  ] for item in sublist] + [
  ('source_file', _get_archive_source_path),
  ('isa_dir', _get_archive_isa_dir)
])
# def export_isa(config : Config, walked, rlist_variant: RepositoryLists = None, name = None):
#   config.log.export.primary("Starting export process for base task")
#   output = StringIO()
#   writer = csv.writer(output)
#   writer.writerow(_csv_structure_base.keys())
#   files = []
#   for repo, file_jsons in walked:
#     repo_stats = load_repo_stats(config, repo)
#     commit_sha = repo_commit_sha(config, repo)
#     for file_json, license_sources in file_jsons:
#       if file_has_stats(repo_stats, file_json):
#         file_stat = file_stats(repo_stats, file_json)
#
#         writer.writerow([func(BaseExportInputs(config, file_stat, commit_sha, repo, license_sources, repo_stats))
#                          for func in _csv_structure_base.values()])
#
#         files.append((file_path(config, repo, file_json),
#                       _license_prefix(config, file_stat, license_sources) + '/' + file_stat['hash']))
#
#
#   config.log.export.primary("Contents calculated, writing zip file")
#   try:
#     export_path = export_file_path(config, rlist_variant, name)
#     export_path.parent.mkdir(exist_ok=True, parents=True)
#     with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
#       zipf.writestr('stats.csv', output.getvalue())
#       for file, new_name in files:
#         zipf.write(file, new_name)
#   except Exception as e:
#     config.log.export.primary(f"Failed to write zip file: {e}")
#     raise e