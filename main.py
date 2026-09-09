import subprocess

from src import export, analyse_file, stats, repository_lists, compile
from src.config import Config
from src.user_dialoge import query, invalid_to_no, terminate, terminate_on_fail, no_to_invalid

from src.repository_lists import RepositoryLists

from src.config import load_config

import argparse

parser = argparse.ArgumentParser(description='HLSL files collection from github, sorting by licenses, decompiling')
parser.add_argument('--config', help='Config file', default='config.json')
parser.add_argument('--filter-size', help='Minimum file size (bytes)', default=0, type=int)
parser.add_argument('--filter-lines', help='Minimum file linecount', default=0, type=int)

args = parser.parse_args()

try:
  config = load_config(args.config)
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

if not recalc_stats and invalid_to_no(query("Recalculate file stats")):
  recalc_stats = True

if recalc_stats:
  for repo, file_jsons in walked:
    update_basic_stats(config, repo, [fj[0] for fj in file_jsons], recalculate=recalc_stats)
  calculate_license_stats(config, walked)


conc = _filter_file_conclusive(walked)
print(f"{len(flatten_removing_repos(conc))} files have conclusive licenses")

from src.filter import filter, new_filter_size, new_filter_line_count, new_filter_unique_hash, filter_has_stats,\
  filter_is_shader

from collections import OrderedDict
filters = OrderedDict([
  ("Have calculated stats", filter_has_stats),
  ("Are shader files (by extension)", filter_is_shader),
  (f"Are bigger than {args.filter_size} bytes", new_filter_size(args.filter_size)),
  (f"Have more than {args.filter_lines} lines", new_filter_line_count(args.filter_lines)),
  (f"Have unique hash", new_filter_unique_hash(config))
])

from src.filter import  FilterBlacklisted
filtered = filter(config, conc, list(filters.values()), [FilterBlacklisted.Blacklisted])

print(f"{len(flatten_removing_repos(filtered))} files:")
for filter_desc in filters:
  print(f"- {filter_desc}")
print("- Not in blacklisted repos")

def report_by_license(walked_):
  permissive, gpl, nonedet, other = _sort_file_conclusive(config, walked_)

  print(f"permissive: {len(flatten_removing_repos(permissive))}, gpl : {len(flatten_removing_repos(gpl))} "
        f"None: {len(flatten_removing_repos(nonedet))}, other: {len(flatten_removing_repos(other))}")

print("By license type:")
report_by_license(filtered)

from src.filter import new_filter_file_extensions, new_filter_platform, new_filter_shader_type, new_no_platform,\
  new_no_shader_type


no_platform = filter(config, filtered, [new_no_platform()])
print(f"From these, {len(flatten_removing_repos(no_platform))} files are not associated with any platform (Unity, etc)")

from src.filter import new_filter_selected_licenses, FilterBlacklisted
from src.config import LicenseGroup

all_good_licenses = filter(config, no_platform,
                           [new_filter_selected_licenses(
                             [LicenseGroup.Permissive, LicenseGroup.GPL, LicenseGroup.NoIncludes],
                             filter_includes=True)],
                           [FilterBlacklisted.Blacklisted])

print(f"From these, {len(flatten_removing_repos(all_good_licenses))} files have permissive/gpl licenses,"
      f" both themselves and includes. Also removed files with missing includes.")
report_by_license(all_good_licenses)

if invalid_to_no(query("(Re)Calculate entry points and compilation targets (will also preprocess)")):
  compile.preprocess(config, all_good_licenses, only_missing=True)
  analyse_file.calculate_vanilla_compilation_parameters(config, all_good_licenses)

if invalid_to_no(query("Compile")):
  compile.compile(config, all_good_licenses, skip_successful=True)
stats.compilation_stats(config, all_good_licenses)

if invalid_to_no(query("Export base files and stats (Includes compilation data, but also all filtered files)")):
  analyse_file.mark_compiled(config, all_good_licenses)
  export.export_base(config, filtered, rlist_variant)

if invalid_to_no(query("Decompile to isa")):
  from src.utils import Decompilers
  compile.decompile(config, all_good_licenses, [Decompilers.RGA, Decompilers.ISA], skip_successful=True)
stats.decompilation_stats(config, all_good_licenses)

if invalid_to_no(query("Export isa pairs")):
  compile.remove_line_directives(config, all_good_licenses)
  export.export_isa(config, all_good_licenses)

