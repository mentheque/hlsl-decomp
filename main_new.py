import subprocess

import analyse_file
import compile
import export
import repository_lists
import stats
from config import Config
from user_dialoge import query, invalid_to_no, terminate, terminate_on_fail, no_to_invalid

from repository_lists import RepositoryLists

from config import load_config

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
  from git_utils import clone_license_named_and_target_files, repo_dir
  from license_scanning import scancode_and_cache

  #TODO: real number
  for i in range(2):
    repo = rlist[i]
    try:
      clone_license_named_and_target_files(config, repo)
      scancode_and_cache(config, repo)
    except Exception as e:
      config.log.licenses.primary(f"Failed on repo {repo.name}, {i} with {e}")


from license_scanning import _walk_repos, _filter_file_conclusive, _sort_file_conclusive,\
  flatten_removing_repos

walked, _ = _walk_repos(config, rlist)

from analyse_file import update_basic_stats, load_repo_stats
from analyse_file import calculate_license_stats

#recalc_stats = False

if recalc_stats:
  for repo, file_jsons in walked:
    update_basic_stats(config, repo, [fj[0] for fj in file_jsons], recalculate=recalc_stats)
  calculate_license_stats(config, walked)

# for repo, file_jsons in walked:
#   stats = load_repo_stats(config, repo)
#   for stat in stats:
#     print(stat)

from git_utils import repo_commit_sha
from utils import reponameless_path

#for repo, file_jsons in walked:
 # blob_prefix = repo.blobs_url.replace("{/sha}", '/' + repo_commit_sha(config, repo)) + '/'
  #for file_json, _ in file_jsons:
    #print(blob_prefix + reponameless_path(file_json))


conc = _filter_file_conclusive(walked)

from filter import filter, new_filter_size, new_filter_line_count, new_filter_unique_hash, filter_has_stats,\
  filter_is_shader

filtered = filter(config, conc, [filter_has_stats, filter_is_shader, new_filter_size(0), new_filter_line_count(0),
                                 new_filter_unique_hash(config)])

permissive, gpl, nonedet, other = _sort_file_conclusive(config, filtered)

print(f"permissive: {len(flatten_removing_repos(permissive))}, gpl : {len(flatten_removing_repos(gpl))} "
      f"None: {len(flatten_removing_repos(nonedet))}, other: {len(flatten_removing_repos(other))}")

from filter import new_filter_file_extensions, new_filter_platform, new_filter_shader_type, new_no_platform,\
  new_no_shader_type
#
# from config import LicenseGroup
# for spisok, name, expectedLT in [(permissive, "permissive", LicenseGroup.Permissive),
#                                  (nonedet, "None", LicenseGroup.Unidentified), (other, "other", LicenseGroup.Other),
#                                  (gpl, "gpl", LicenseGroup.GPL)]:
#   print(f"------ {name} ---------")
#   from analyse_file import _platforms, _shader_types
#   for platform in (_platforms + ["no"]):
#     platform_specific = []
#     if platform == "no":
#       platform_specific =  filter(config, spisok, [new_no_platform()])
#     else:
#       platform_specific = filter(config, spisok, [new_filter_platform(platform)])
#     print(f"++ {platform}: {len(flatten_removing_repos(platform_specific))}")
#     for shader_type in (_shader_types + ["no"]):
#       filters = []
#       if shader_type == "no":
#         filters = [new_no_shader_type()]
#       else:
#         filters = [new_filter_shader_type(shader_type)]
#       print(f"{shader_type}: "
#             f"{len(flatten_removing_repos(filter(config, platform_specific, filters)))}")
#
#   from analyse_file import file_stats
#   for repo, file_jsons in spisok:
#     repo_stats = load_repo_stats(config, repo)
#     for file_json, _ in file_jsons:
#       if file_stats(repo_stats, file_json)['license'] != expectedLT:
#         print("!!!! WTF")
#
#   print(f"{name}, cginc: {len(flatten_removing_repos(filter(config, spisok, [ new_filter_file_extensions(['cginc'])])))}")
#   print(f"{name}, unreal: {len(flatten_removing_repos(filter(config, spisok, [ new_filter_file_extensions(['ush', 'usf'])])))}")
#   print(f"{name}, hlsl(i): {len(flatten_removing_repos(filter(config, spisok, [ new_filter_file_extensions(['hlsl', 'hlsli'])])))}")
#   print(f"{name}, fx(h): {len(flatten_removing_repos(filter(config, spisok, [ new_filter_file_extensions(['fx', 'fxh'])])))}")


no_platform = filter(config, filtered, [new_no_platform()])


from filter import new_filter_selected_licenses, FilterBlacklisted
from config import LicenseGroup

all_good_licenses = filter(config, no_platform,
                           [new_filter_selected_licenses(
                             [LicenseGroup.Permissive, LicenseGroup.GPL, LicenseGroup.NoIncludes],
                             filter_includes=True)],
                           [FilterBlacklisted.Blacklisted])
from analyse_file import calculate_vanilla_compilation_parameters

permissive, gpl, nonedet, other = _sort_file_conclusive(config, all_good_licenses)

print(f"permissive: {len(flatten_removing_repos(permissive))}, gpl : {len(flatten_removing_repos(gpl))} "
      f"None: {len(flatten_removing_repos(nonedet))}, other: {len(flatten_removing_repos(other))}")


from analyse_file import file_stats
for repo, file_jsons in all_good_licenses:
  repo_stats = load_repo_stats(config, repo)

  for file_json, _ in file_jsons:
    if file_stats(repo_stats, file_json)['hash'] == '82a697181118d6e81a8161fe85b3e2d4618f78c1b6b647926fe14091320b303e':
      print("Should be here!!")

    if file_stats(repo_stats, file_json)['hash'] == 'be3f29cfb82ea841cbb5f2bf2675161917707db2fa5f20223e3bbd52d1e17b8b' \
      or file_stats(repo_stats, file_json)['worst_included_license'] \
      not in [LicenseGroup.Permissive, LicenseGroup.GPL, LicenseGroup.NoIncludes]:
      print("!! WTF")


from compile import preprocess

#preprocess(config, all_good_licenses, only_missing=True)

#calculate_vanilla_compilation_parameters(config, all_good_licenses, specific_shader_types=['compute', 'vertex'])
                                        #, specific_shader_types=['compute'],
                                        # excluded_repos=['clshortfuse/renodx', 'NotVoosh/renodx-unity'])

#export.export_base(config, filtered, rlist_variant = rlist_variant, name ="all_licenses_conclusive")

#compile.compile(config, all_good_licenses)

#analyse_file.mark_compiled(config, all_good_licenses)

#stats.compilation_stats(config, all_good_licenses)


# res = subprocess.run(
#   [config.decompilator_paths['rga'],
#    '-s', 'dx11',
# '--asic', 'gfx1030',
#    '--isa', str(save_path),
#    '--dxbc', "C:/Users/menth/Documents/compiled/68e405dcce5ade20d1a8eb45b665a0ff60e8e5945805be16793e8305f0e9de56_ps_4_0_main"
#    ]
# , capture_output=True, text=True, check=True)

# save_path = join_path(config.decompiled_dir, 'amd/6767')
# save_path.parent.mkdir(parents=True, exist_ok=True)
# res_6 = subprocess.run(
#   [config.decompilator_paths['rga'],
#    '-s', f'vk-spv-offline',
#     #'-c', 'gfx1100',
#    '--isa', str(save_path) + '/',
# '--comp', "C:/Users/menth/Documents/5df75fe1ea9c2ae5f3b6738bde0ac4ffd3ce070405bc31bf65c451e740014373_cs_6_3_CopyToFinal_spirv.spv"
#    ]
# , capture_output=True, text=True, check=True)
#
# print(res_6.returncode)
# print(res_6.stdout)
# print(res_6.stderr)

from utils import Decompilers
compile.decompile(config, all_good_licenses, [Decompilers.ISA])

