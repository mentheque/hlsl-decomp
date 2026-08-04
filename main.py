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

# This needs to happen before filtering bad files out, and seems to had been happening there before.
# also, add license information in there too.
from analyse_file import update_stats, load_repo_stats
from utils import extention_case_variations


for repo, file_jsons in walked:
  update_stats(config, repo, [fj[0] for fj in file_jsons], recalculate=True)
  repo_stats = load_repo_stats(config, repo)
  for file, stat in repo_stats.items():
    if 'is_shader' not in stat.keys():
      continue

    if not stat['is_shader']:
      continue

    print(f"File: {repo_dir(config, repo)}/{file}")
    print(stat['platforms'])
    print(stat['shader_type'])
    #
    # print("Includes: ")
    # for include in stat['includes']:
    #   print(include)
    #   if include in repo_stats:
    #       found = True
    #       print(repo_stats[include]['platforms'])
    #   else:
    #     # NOTE:
    #     # - made include search case-insensitive as may be expected
    #     # - search for includes correctly handles #ifdef __cplusplus and related directives
    #     # - Some libraries will still fail, as there is hardly a way to find intended -I compiler flag if not by hand.
    #     # - Also, some people apparently use .psh and .vsh, but for the files already downloaded this has been a problem
    #     # For a single repository only. So safe to say it's either not very popular or styles don't intersect.
    #     # Since I don't want to guess the language of any specific file, I will live such ambiguous extensions out.
    #     print("!!! WARNING: include not analysed !!!")

permissive, gpl, nonedet, other = _sort_file_conclusive(config, _filter_file_conclusive(walked))

print(f"permissive: {len(flatten_removing_repos(permissive))}, gpl : {len(flatten_removing_repos(gpl))} "
      f"None: {len(flatten_removing_repos(nonedet))}, other: {len(flatten_removing_repos(other))}")

from filter import filter, new_filter_size, new_filter_line_count, new_filter_unique_hash, filter_has_stats,\
  filter_is_shader

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
                                                       filter_is_shader,
                                                       new_filter_line_count(min_lines=0),
                                                       new_filter_size(min_size=1024*0),
                                                       new_filter_unique_hash(config)]))

print(f"permissive: {len(flatten_removing_repos(permissive))}, gpl : {len(flatten_removing_repos(gpl))} "
      f"None: {len(flatten_removing_repos(nonedet))}, other: {len(flatten_removing_repos(other))}")

from filter import new_filter_file_extensions, new_filter_platform, new_filter_shader_type, new_no_platform,\
  new_no_shader_type

for spisok, name in [(permissive, "permissive"), (nonedet, "None"), (other, "other"), (gpl, "gpl")]:
  print(f"------ {name} ---------")
  from analyse_file import _platforms, _shader_types
  for platform in (_platforms + ["no"]):
    platform_specific = []
    if platform == "no":
      platform_specific =  filter(config, spisok, [new_no_platform()])
    else:
      platform_specific = filter(config, spisok, [new_filter_platform(platform)])
    print(f"++ {platform}: {len(flatten_removing_repos(platform_specific))}")
    for shader_type in (_shader_types + ["no"]):
      filters = []
      if shader_type == "no":
        filters = [new_no_shader_type()]
      else:
        filters = [new_filter_shader_type(shader_type)]
      print(f"{shader_type}: "
            f"{len(flatten_removing_repos(filter(config, platform_specific, filters)))}")

  print(f"{name}, cginc: {len(flatten_removing_repos(filter(config, spisok, [ new_filter_file_extensions(['cginc'])])))}")
  print(f"{name}, unreal: {len(flatten_removing_repos(filter(config, spisok, [ new_filter_file_extensions(['ush', 'usf'])])))}")
  print(f"{name}, hlsl(i): {len(flatten_removing_repos(filter(config, spisok, [ new_filter_file_extensions(['hlsl', 'hlsli'])])))}")
  print(f"{name}, fx(h): {len(flatten_removing_repos(filter(config, spisok, [ new_filter_file_extensions(['fx', 'fxh'])])))}")


permissive_none_detected = filter(config, permissive, [new_no_platform(), new_no_shader_type()])
print("-------- Permissive files with no type detected -----------")
for repo, file_jsons in permissive_none_detected:
  for file_json in file_jsons:
    print(f"{repo_dir(config, repo)}/{file_json[0]['path']}")
