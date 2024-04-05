###############################################################################
#
# (c) 2024 Schneider Electric SE. All rights reserved.
# All trademarks are owned or licensed by Schneider Electric SAS,
# its subsidiaries or affiliated companies.
#
###############################################################################

import argparse
import logging
import os
import pathlib
import stat
import sys
import threading
import time
from typing import Dict

import keyring
from git import Repo
from github import Auth, Github
from lxml import etree

KEYRING_SERVICE_NAME = "GITHUB_PAT"
KEYRING_USER_NAME = "GITHUB_PAT_USER"

KEYRING_SERVICE_NAME_GHE = "GHE_PAT"
KEYRING_USER_NAME_GHE = "GHE_PAT_USER"

PAT = None
GHE_PAT = None


def build_parser():
    """ Build argument parser. """

    parser = argparse.ArgumentParser(
        description='Tool to clone Libra repo'
    )
    parser.add_argument(
        '-u', '--url', dest='url',
        help='Repo Manifest URL'
    )
    parser.add_argument(
        '--init', dest='init', action="store_true",
        help='Initialize the repos'
    )
    parser.add_argument(
        '--sync', dest='sync', action="store_true",
        help='Sync the repos'
    )
    parser.add_argument(
        '--start', dest='start', action="store_true",
        help='Switch repos to branch'
    )
    parser.add_argument(
        '-b', dest='branch',
        help='Branch of the repo manifest to pull'
    )
    parser.add_argument(
        '-d', '--dst', dest='dst',
        help='Destination of repo'
    )
    parser.add_argument(
        '--status', dest='status', action="store_true",
        help='Branch status of repo'
    )
    parser.add_argument(
        '--pat', dest='pat',
        help='GitHub PAT (Queried from WCM if not provided)'
    )
    parser.add_argument(
        '--ghe-pat', dest='ghe_pat',
        help='GitHub Enterprise PAT (Queried from WCM if not provided)'
    )

    return parser


def clean_dst(dst_folder: pathlib.Path):
    """ clean the dst folder """

    def rmtree(top: pathlib.Path):
        """ os walk to remove files and dir """

        for root, dirs, files in os.walk(top, topdown=False):

            for name in files:
                filename = os.path.join(root, name)
                os.chmod(filename, stat.S_IWUSR)
                os.remove(filename)

            for name in dirs:
                os.rmdir(os.path.join(root, name))

        os.rmdir(top)

    if os.path.exists(dst_folder):
        rmtree(dst_folder)

    pathlib.Path(dst_folder).mkdir(exist_ok=True)


def get_pat(ghe: bool = False):
    """ Get PAT from WCM """

    if not ghe:
        pat = keyring.get_password(KEYRING_SERVICE_NAME,
                                   KEYRING_USER_NAME)

    else:
        pat = keyring.get_password(KEYRING_SERVICE_NAME_GHE,
                                   KEYRING_USER_NAME_GHE)

    if pat is None:
        raise Exception("No GitHub PAT or GHE PAT not provided or found in WCM. "
                        "Please provide a PAT or run the PAT manager tool. "
                        "https://github.com/SchneiderProsumer/test-project-credential-manager")

    return pat


def init_repo(url: str,
              branch: str = "main",
              repo_folder: str = ".manifest",
              manifest_file_name: str = "default.xml",
              dst_folder: str = os.getcwd()):
    """ Get repo manifest file """

    hostname = url.replace('.git', '').split('://')[-1].split('/', 1)[0].split("@")[-1]
    repo_link = url.replace('.git', '').split('://')[-1].split('/', 1)[-1]

    pat = get_pat()

    git = Github(base_url=f"https://api.{hostname}", auth=Auth.Token(pat))
    repo = git.get_repo(repo_link)
    branch = repo.get_branch(branch)

    file_content = repo.get_contents(manifest_file_name, ref=branch.commit.sha)

    if os.path.exists(pathlib.Path(dst_folder) / repo_folder):
        clean_dst(pathlib.Path(dst_folder) / repo_folder)

    os.mkdir(pathlib.Path(dst_folder) / repo_folder)

    text = file_content.decoded_content.decode("utf-8", errors="ignore")
    with open(pathlib.Path(dst_folder) / repo_folder / manifest_file_name, "w") as f:
        f.write(text)
        f.flush()


def create_mapping(dst_path: str = os.getcwd(),
                   repo_folder: str = ".manifest",
                   manifest_file_name: str = "default.xml"):
    """ Clone the repo manifest """

    repo_path = pathlib.Path(dst_path) / repo_folder / manifest_file_name

    try:
        with open(repo_path, 'r') as f:
            file_content = f.read()

    except FileNotFoundError as err:
        raise FileNotFoundError(f"{err}\nManifest file missing. Run with --init flag")

    repo_manifest = etree.fromstring(file_content.encode())

    remote_tag = repo_manifest.findall('.//remote')
    default_tag = repo_manifest.findall('.//default')[0]
    project_tag = repo_manifest.findall('.//project')

    mapping = {}
    for item in project_tag:

        if item.attrib["name"] not in mapping:
            mapping[item.attrib["name"]] = {}

        mapping[item.attrib["name"]]["path"] = item.attrib["path"]

        if "revision" not in item.attrib:
            mapping[item.attrib["name"]]["revision"] = default_tag.attrib["revision"]

        else:
            mapping[item.attrib["name"]]["revision"] = item.attrib["revision"]

        if "remote" not in item.attrib:
            mapping[item.attrib["name"]]["remote"] = default_tag.attrib["remote"]

        else:
            mapping[item.attrib["name"]]["remote"] = item.attrib["remote"]

        for tag in remote_tag:
            remote_name = tag.attrib["name"]
            if remote_name == mapping[item.attrib["name"]]["remote"]:
                mapping[item.attrib["name"]]["remote"] = tag.attrib["fetch"]

    return mapping


def sync_repos(manifest: Dict, dst_path: str = os.getcwd()):
    """ Sync GitHub repos from manifest file """

    def clone_repo(path: str, repo_data: Dict, dst_path: str):
        """ Clone repo to dst path """

        pat = get_pat(ghe="schneider-electric" in repo_data["remote"])
        hostname = repo_data["remote"].split("://")[-1]
        dst_path = pathlib.Path(dst_path) / repo_data["path"]
        url = f"https://{pat}@{hostname}/{path}.git"

        if os.path.exists(dst_path):

            logging.info(f"Pulling repo {url.replace(pat, '*****')} "
                         f"branch {repo_data['revision']}")
            repo = Repo(dst_path)
            repo.git.checkout(repo_data["revision"])

        else:

            logging.info(f"Cloning repo {url.replace(pat, '*****')}")
            Repo.clone_from(url, dst_path, branch=repo_data["revision"])

    if manifest is None:
        raise Exception("Manifest file mapping missing run with --init flag")

    threads = {}
    for repo_path, repo_info in manifest.items():

        count = repo_info["path"].count('/')

        if count not in threads:
            threads[count] = []

        task_thread = threading.Thread(target=clone_repo,
                                       args=(repo_path, repo_info, dst_path),
                                       daemon=True)

        threads[count].append(task_thread)

    for count in threads:
        for thread in threads[count]:
            thread.start()
        time.sleep(1)

    for count in threads:
        for thread in threads[count]:
            thread.join()


def repo_status(repo_mapping: dict,
                dst_path: str = os.getcwd()):
    """ print status of repos """

    max_branch_len = -1

    for repo_path, repo_info in repo_mapping.items():
        path = pathlib.Path(dst_path) / repo_info["path"]
        if len(Repo(path).active_branch.name) > max_branch_len:
            max_branch_len = len(Repo(path).active_branch.name)

    for repo_path, repo_info in repo_mapping.items():
        path = pathlib.Path(dst_path) / repo_info["path"]
        branch = Repo(path).active_branch.name
        branch = branch.ljust(max_branch_len + 3, ' ')
        logging.info(f"{branch}{repo_path}")


def start_repos(repo_mapping: dict,
                branch: str = "main",
                dst_path: str = os.getcwd()):
    """ Start the repo on branch """


def main():
    parser = build_parser()
    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    logging.basicConfig(datefmt="%Y-%m-%d %H:%M:%S",
                        format="[%(asctime)s.%(msecs)03d] %(levelname)s: %(message)s",
                        stream=sys.stdout,
                        level=logging.INFO)

    if args.pat:
        keyring.set_password(KEYRING_SERVICE_NAME,
                             KEYRING_USER_NAME,
                             args.pat)
        logging.info("GitHub PAT added to WCM!")

    if args.ghe_pat:
        keyring.set_password(KEYRING_SERVICE_NAME_GHE,
                             KEYRING_USER_NAME_GHE,
                             args.pat)
        logging.info("GitHub Enterprise PAT added to WCM!")

    dst_folder = os.getcwd()
    if args.dst:
        dst_folder = args.dst

    branch = args.branch
    if branch is None:
        branch = "main"

    if args.init:
        if pathlib.Path(dst_folder) != pathlib.Path(__file__).resolve().parent:
            clean_dst(dst_folder)

        init_repo(args.url, branch, dst_folder=dst_folder)

    if args.sync:
        manifest_mapping = create_mapping(dst_path=dst_folder)
        sync_repos(manifest_mapping, dst_path=dst_folder)

    if args.start:
        manifest_mapping = create_mapping(dst_path=dst_folder)
        start_repos(manifest_mapping, args.start, dst_folder)

    if args.status:
        manifest_mapping = create_mapping(dst_path=dst_folder)
        repo_status(manifest_mapping, dst_folder)


if __name__ == '__main__':
    main()
