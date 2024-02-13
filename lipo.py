###############################################################################
#
# (c) 2023 Schneider Electric SE. All rights reserved.
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

import keyring
from github import Auth, Github

KEYRING_SERVICE_NAME = "GITHUB_PAT"
KEYRING_USER_NAME = "GITHUB_PAT_USER"


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
        '--pat', dest='pat',
        help='Use GitHub Personal Access Token'
    )
    parser.add_argument(
        '-b', dest='branch',
        help='Branch of the repo manifest to pull'
    )
    parser.add_argument(
        '-v', dest='verbose', action="store_true",
        help='Run with verbose level DEBUG'
    )

    return parser


def check_pat(pat: str):
    """  """

    if pat is None:
        logging.debug("PAT not provided checking PAT in WCM")

        pat = keyring.get_password(KEYRING_SERVICE_NAME,
                                   KEYRING_USER_NAME)

    if pat is None:
        raise Exception("No GitHub PAT provided (--pat <PAT>) or found in WCM. "
                        "Please provide a PAT or run the PAT manager tool. "
                        "https://github.com/SchneiderProsumer/test-project-credential-manager")

    return pat


def create_repo_manifest(url: str,
                         base_path: pathlib.Path,
                         pat: str,
                         branch: str = "main"):
    """ Clone the repo manifest """

    repo_manifest_folder = ".repo"

    # create folder for manifest
    if os.path.exists(base_path / repo_manifest_folder):
        shutil.rmtree(base_path / repo_manifest_folder)

    hostname = url.strip(".git").split('://')[-1].split('/', 1)[0]
    repo_link = url.strip(".git").split('://')[-1].split('/', 1)[-1]

    pat = check_pat(pat)
    git = Github(base_url=f"https://api.{hostname}", auth=Auth.Token(pat))
    repo = git.get_repo(repo_link)

    x = 0


def main():
    parser = build_parser()
    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    logging.basicConfig(datefmt="%Y-%m-%d %H:%M:%S",
                        format="[%(asctime)s.%(msecs)03d] %(levelname)s: %(message)s",
                        stream=sys.stdout,
                        level=logging.INFO if not args.verbose else logging.DEBUG)

    pat = None
    if args.pat:
        pat = args.pat

    if args.init:
        create_repo_manifest(args.url, pathlib.Path(os.getcwd()), pat)


if __name__ == '__main__':
    main()
