import subprocess

from src import export, analyse_file, stats, repository_lists, compile
from src.config import Config
from src.user_dialoge import query, invalid_to_no, terminate, terminate_on_fail, no_to_invalid

from src.repository_lists import RepositoryLists

from src.config import load_config

try:
  config = load_config()
except Exception as e:
  terminate("Failed to load config")

from collections import OrderedDict
_list_variants = OrderedDict([
  ('Full', RepositoryLists.Full),
  ('Top starred (1000)', RepositoryLists.TopStarred),
  ('Repositories w selected licenses (from config)', RepositoryLists.SelectedLicenses)
])

rlist_variant = list(_list_variants.values())[
  terminate_on_fail(query("Repository list", _list_variants.keys()), "Repository list not chosen")]

rlist = None
try:
  rlist = repository_lists.load(config, rlist_variant)
except FileNotFoundError:
  print("File not found, attempting to parse from github.")
except Exception as e:
  terminate_on_fail(no_to_invalid(
    query(f"Failed to load list: {e}. Parse from github")), "Unable to load repository list")

if rlist is None:
  try:
    rlist = repository_lists.gh_get(config, rlist_variant)
  except Exception as e:
    terminate(f"Parsing list from gh failed with {e}")

recalc_stats = False
if invalid_to_no(query("List is loaded. (Re)download files and scan for licenses")):
  recalc_stats = True
  from src.git_utils import clone_license_named_and_target_files, repo_dir
  from src.license_scanning import scancode_and_cache

  #TODO: real number
  for i in range(2):
    repo = rlist[i]
    try:
      clone_license_named_and_target_files(config, repo)
      scancode_and_cache(config, repo)
    except Exception as e:
      config.log.licenses.primary(f"Failed on repo {repo.name}, {i} with {e}")


from src.license_scanning import _walk_repos, _filter_file_conclusive, _sort_file_conclusive,\
  flatten_removing_repos

walked, _ = _walk_repos(config, rlist)

from src.analyse_file import update_basic_stats, load_repo_stats
from src.analyse_file import calculate_license_stats

#recalc_stats = False

if recalc_stats:
  for repo, file_jsons in walked:
    update_basic_stats(config, repo, [fj[0] for fj in file_jsons], recalculate=recalc_stats)
  calculate_license_stats(config, walked)

# for repo, file_jsons in walked:
#   stats = load_repo_stats(config, repo)
#   for stat in stats:
#     print(stat)

from src.git_utils import repo_commit_sha
from src.utils import reponameless_path

#for repo, file_jsons in walked:
 # blob_prefix = repo.blobs_url.replace("{/sha}", '/' + repo_commit_sha(config, repo)) + '/'
  #for file_json, _ in file_jsons:
    #print(blob_prefix + reponameless_path(file_json))


conc = _filter_file_conclusive(walked)

from src.filter import filter, new_filter_size, new_filter_line_count, new_filter_unique_hash, filter_has_stats,\
  filter_is_shader

filtered = filter(config, conc, [filter_has_stats, filter_is_shader, new_filter_size(0), new_filter_line_count(0),
                                 new_filter_unique_hash(config)])

permissive, gpl, nonedet, other = _sort_file_conclusive(config, filtered)

print(f"permissive: {len(flatten_removing_repos(permissive))}, gpl : {len(flatten_removing_repos(gpl))} "
      f"None: {len(flatten_removing_repos(nonedet))}, other: {len(flatten_removing_repos(other))}")

from src.filter import new_filter_file_extensions, new_filter_platform, new_filter_shader_type, new_no_platform,\
  new_no_shader_type


no_platform = filter(config, filtered, [new_no_platform()])


from src.filter import new_filter_selected_licenses, FilterBlacklisted
from src.config import LicenseGroup

all_good_licenses = filter(config, no_platform,
                           [new_filter_selected_licenses(
                             [LicenseGroup.Permissive, LicenseGroup.GPL, LicenseGroup.NoIncludes],
                             filter_includes=True)],
                           [FilterBlacklisted.Blacklisted])
from src.analyse_file import calculate_vanilla_compilation_parameters

permissive, gpl, nonedet, other = _sort_file_conclusive(config, all_good_licenses)

print(f"permissive: {len(flatten_removing_repos(permissive))}, gpl : {len(flatten_removing_repos(gpl))} "
      f"None: {len(flatten_removing_repos(nonedet))}, other: {len(flatten_removing_repos(other))}")


from src.analyse_file import file_stats
for repo, file_jsons in all_good_licenses:
  repo_stats = load_repo_stats(config, repo)

  for file_json, _ in file_jsons:
    if file_stats(repo_stats, file_json)['hash'] == '82a697181118d6e81a8161fe85b3e2d4618f78c1b6b647926fe14091320b303e':
      print("Should be here!!")

    if file_stats(repo_stats, file_json)['hash'] == 'be3f29cfb82ea841cbb5f2bf2675161917707db2fa5f20223e3bbd52d1e17b8b' \
      or file_stats(repo_stats, file_json)['worst_included_license'] \
      not in [LicenseGroup.Permissive, LicenseGroup.GPL, LicenseGroup.NoIncludes]:
      print("!! WTF")

from src.utils import Decompilers
compile.decompile(config, all_good_licenses, [Decompilers.RGA, Decompilers.ISA], skip_successful=True)
#stats.decompilation_stats(config, all_good_licenses)
#compile.remove_line_directives(config, all_good_licenses)
#export.export_isa(config, all_good_licenses)

