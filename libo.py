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
import shutil
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


def build_parser():
    """ Build argument parser. """

    parser = argparse.ArgumentParser(
        description='Tool to clone Libra repo'
    )
    parser.add_argument(
        '-u', '--url', dest='url',
        help='Repo Manifest URL', required=True
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

    return parser


def get_pat(ghe: bool = False):
    """ Get PAT from WCM """

    if not ghe:
        pat = keyring.get_password(KEYRING_SERVICE_NAME,
                                   KEYRING_USER_NAME)

    else:
        pat = keyring.get_password(KEYRING_SERVICE_NAME_GHE,
                                   KEYRING_USER_NAME_GHE)

    if pat is None:
        raise Exception("No GitHub PAT or GHE PAT found in WCM. "
                        "Please provide a PAT or run the PAT manager tool. "
                        "https://github.com/SchneiderProsumer/test-project-credential-manager")

    return pat


def init_repo(url: str,
              branch: str = "main",
              repo_folder: str = ".repo",
              manifest_file_name: str = "default.xml"):
    """ Get repo manifest file """

    current_base_path = pathlib.Path(os.getcwd())

    hostname = url.strip(".git").split('://')[-1].split('/', 1)[0]
    repo_link = url.strip(".git").split('://')[-1].split('/', 1)[-1]

    pat = get_pat()
    git = Github(base_url=f"https://api.{hostname}", auth=Auth.Token(pat))
    repo = git.get_repo(repo_link)
    branch = repo.get_branch(branch)

    file_content = repo.get_contents(manifest_file_name, ref=branch.commit.sha)

    if os.path.exists(current_base_path / repo_folder):
        shutil.rmtree(current_base_path / repo_folder)
    os.mkdir(current_base_path / repo_folder)

    text = file_content.decoded_content.decode("utf-8", errors="ignore")
    with open(current_base_path / repo_folder / manifest_file_name, "w") as f:
        f.write(text)
        f.flush()


def get_repo_manifest(repo_folder: str = ".repo",
                      manifest_file_name: str = "default.xml"):
    """ Clone the repo manifest """

    repo_path = pathlib.Path(os.getcwd()) / repo_folder / manifest_file_name

    try:
        with open(repo_path, 'r') as f:
            file_content = f.read()

    except FileNotFoundError as err:
        raise FileNotFoundError(f"{err}\nManifest file missing. Run with --init flag")

    repo_manifest = etree.fromstring(file_content.encode())

    remote_tag = repo_manifest.findall('.//remote')
    default_tag = repo_manifest.findall('.//default')[0]
    project_tag = repo_manifest.findall('.//project')

    manifest_mapping = {}
    for item in project_tag:

        if item.attrib["name"] not in manifest_mapping:
            manifest_mapping[item.attrib["name"]] = {}

        manifest_mapping[item.attrib["name"]]["path"] = item.attrib["path"]

        if "revision" not in item.attrib:
            manifest_mapping[item.attrib["name"]]["revision"] = default_tag.attrib["revision"]

        else:
            manifest_mapping[item.attrib["name"]]["revision"] = item.attrib["revision"]

        if "remote" not in item.attrib:
            manifest_mapping[item.attrib["name"]]["remote"] = default_tag.attrib["remote"]

        else:
            manifest_mapping[item.attrib["name"]]["remote"] = item.attrib["remote"]

        for tag in remote_tag:
            remote_name = tag.attrib["name"]
            if remote_name == manifest_mapping[item.attrib["name"]]["remote"]:
                manifest_mapping[item.attrib["name"]]["remote"] = tag.attrib["fetch"]

    return manifest_mapping


def sync_repos(manifest: Dict):
    """ Sync GitHub repos from manifest file """

    def clone_repo(path: str, repo: Dict):
        """ Clone repo to dst path """

        pat = get_pat(ghe="schneider-electric" in repo["remote"])
        hostname = repo["remote"].split("://")[-1]
        dst_path = pathlib.Path(os.getcwd()) / repo["path"]
        url = f"https://{pat}@{hostname}/{path}.git"

        logging.info(f"Cloning {url}")
        Repo.clone_from(url, dst_path, branch=repo["revision"])

    if manifest is None:
        raise Exception("Manifest file mapping missing run with --init flag")

    threads = {}
    for repo_path, repo in manifest.items():

        count = repo["path"].count('/')

        if count not in threads:
            threads[count] = []

        task_thread = threading.Thread(target=clone_repo, args=(repo_path, repo), daemon=True)

        threads[count].append(task_thread)

    for count in threads:
        for thread in threads[count]:
            thread.start()
        time.sleep(1)

    for count in threads:
        for thread in threads[count]:
            thread.join()


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

    branch = args.branch
    if branch is None:
        branch = "main"

    if args.init:
        init_repo(args.url, branch)

    if args.sync:
        manifest_mapping = get_repo_manifest()
        sync_repos(manifest_mapping)


if __name__ == '__main__':
    main()
