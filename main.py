import json
import os.path
import traceback
import time

from logs import ConsoleLogger, PrefixedLogger, EchoLogger
from config import Config, MultiModuleLogger, LicenseType, LicenseGroup

config = \
  Config(
    language="HLSL",
    github_token="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",
    target_file_extensions=['hlsl', 'hlsli', 'cginc', 'fx', 'fxh', 'usf', 'ush'],
    additional_file_extensions=['h'],
    log=MultiModuleLogger(PrefixedLogger("default", EchoLogger(filepath="logs/default_logs.txt"))),
    git_directory="C:/Users/menth/Documents/cloned_repos3",
    scancode_cache_dir="scancode2",
    scancode_processes=6,
    licenses=[
      LicenseType(name, gh_search_name, unique_prefix, group) for name, gh_search_name, unique_prefix, group in
      [
        ("MIT", "MIT", "MIT", LicenseGroup.Permissive),
        ("Apache 2.0", "Apache-2.0", "Apache-2.0", LicenseGroup.Permissive),
        ("BSD 2", "BSD-2-Clause", "BSD", LicenseGroup.Permissive),
        ("BSD 3 new", "BSD-3-Clause", "BSD", LicenseGroup.Permissive),
        ("BSD 3 clear", "BSD-3-Clause-Clear", "BSD", LicenseGroup.Permissive),
        ("BSD 4", "BSD-4-Clause", "BSD", LicenseGroup.Permissive),
        ("BSD 0", "0BSD", "BSD", LicenseGroup.Permissive),
        ("CC0", "CC0-1.0", "CC0", LicenseGroup.Permissive),
        ("Unlicense", "Unlicense", "Unlicense", LicenseGroup.Permissive),
        ("GPL family", "GPL", "GPL", LicenseGroup.GPL)
      ]
    ]
  )

from repository_lists import gh_full_repository_list, gh_top_stars, gh_selected_licenses

# gh_full_repository_list(config)
# gh_selected_licenses(config)
# gh_top_stars(config)

from repository_lists import load_selected_licenses_rlist
loaded = load_selected_licenses_rlist(config)

from git_utils import clone_license_named_and_target_files, repo_dir
from license_scanning import scancode_and_cache
#
# for i in range(977, len(loaded)):
#   repo = loaded[i]
#   try:
#     clone_license_named_and_target_files(config, repo)
#     scancode_and_cache(config, repo)
#   except Exception as e:
#     config.log.licenses.primary(f"Failed on repo {repo.name}, {i}")



from license_scanning import _walk_repo, _walk_repos, _filter_file_conclusive, _sort_file_conclusive,\
  flatten_removing_repos

walked, _ = _walk_repos(config, loaded)
permissive, gpl, nonedet, other = _sort_file_conclusive(config, _filter_file_conclusive(walked))



print(f"permissive: {len(flatten_removing_repos(permissive))}, gpl : {len(flatten_removing_repos(gpl))} "
      f"None: {len(flatten_removing_repos(nonedet))}, other: {len(flatten_removing_repos(other))}")

from filter import filter, new_filter_size, new_filter_line_count, new_filter_unique_hash, filter_has_stats

permissive, gpl, nonedet, other = filter(config, permissive, [filter_has_stats, new_filter_unique_hash(config)]),\
  filter(config, gpl, [filter_has_stats, new_filter_unique_hash(config)]),\
                                                        filter(config, nonedet, [filter_has_stats, new_filter_unique_hash(config)]),\
                             filter(config, other, [filter_has_stats, new_filter_unique_hash(config)])

print(f"permissive: {len(flatten_removing_repos(permissive))}, gpl : {len(flatten_removing_repos(gpl))} "
      f"None: {len(flatten_removing_repos(nonedet))}, other: {len(flatten_removing_repos(other))}")

joint = permissive + gpl + nonedet + other
permissive, gpl, nonedet, other = _sort_file_conclusive(config,
                                                   filter(
                                                     config,
                                                     joint,
                                                     [
                                                       filter_has_stats,
                                                       new_filter_line_count(min_lines=0),
                                                       new_filter_size(min_size=1024*0),
                                                       new_filter_unique_hash(config)]))

print(f"permissive: {len(flatten_removing_repos(permissive))}, gpl : {len(flatten_removing_repos(gpl))} "
      f"None: {len(flatten_removing_repos(nonedet))}, other: {len(flatten_removing_repos(other))}")

from filter import new_filter_file_extensions

for spisok, name in [(permissive, "permissive"), (nonedet, "None"), (other, "other"), (gpl, "gpl")]:
  print(f"{name}, cginc: {len(flatten_removing_repos(filter(config, spisok, [ new_filter_file_extensions(['cginc'])])))}")
  print(f"{name}, unreal: {len(flatten_removing_repos(filter(config, spisok, [ new_filter_file_extensions(['ush', 'usf'])])))}")
  print(f"{name}, hlsl(i): {len(flatten_removing_repos(filter(config, spisok, [ new_filter_file_extensions(['hlsl', 'hlsli'])])))}")
  print(f"{name}, fx(h): {len(flatten_removing_repos(filter(config, spisok, [ new_filter_file_extensions(['fx', 'fxh'])])))}")