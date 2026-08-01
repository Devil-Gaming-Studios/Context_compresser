#!/usr/bin/env python3
"""
Context Compressor CLI -- no server needed.

Usage:
    python cli.py FILE [options]
    python cli.py --repo DIR [options]

Examples:
    python cli.py my_logs.txt
    python cli.py my_logs.txt --target 0.6 --content-type logs
    python cli.py app.py --preset aggressive --out compressed.py
    python cli.py app.py --report report.html
    python cli.py --repo ./my_project --target 0.7
"""

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()  # reads a .env file (e.g. GITHUB_TOKEN) from the current or a parent directory, if present

from context_compressor import ContextCompressor
from context_compressor.diff_export import write_report
from context_compressor.presets import PRESETS
from context_compressor.tokenizer import supported_models


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compress a text/code/log file (or a whole repo) for use as LLM context.",
    )
    parser.add_argument("file", nargs="?", help="Path to the file to compress")
    parser.add_argument("--repo", metavar="DIR", help="Compress every source file under DIR instead of a single file")
    parser.add_argument("--diff", metavar="BASE_REF", nargs="?", const="HEAD",
                         help="Diff-aware mode: compress only what changed vs BASE_REF (default HEAD) plus needed "
                              "context. Reads the repo at --repo (or the current directory if --repo is omitted).")
    parser.add_argument("--diff-target-ref", metavar="REF", default=None,
                         help="Compare BASE_REF..REF instead of BASE_REF..working-tree (used with --diff)")
    parser.add_argument("--diff-file", metavar="PATH",
                         help="Diff-aware mode from a standalone unified diff file (e.g. a GitHub PR's .diff URL "
                              "downloaded to disk) instead of running git. Requires --repo to point at a checkout "
                              "containing the new (post-change) file contents.")
    parser.add_argument("--github-pr", metavar="PR",
                         help="Diff-aware mode, fetched automatically: a GitHub PR URL "
                              "(https://github.com/owner/repo/pull/123) or shorthand owner/repo#123. Fetches the "
                              "diff and changed-file contents itself via the public GitHub API -- no git repo, no "
                              "OAuth. Public repos work out of the box; set GITHUB_TOKEN for private repos or a "
                              "higher rate limit.")
    parser.add_argument("--session", metavar="PATH",
                         help="Session-compression mode: compress a chat/conversation export JSON file (ChatGPT "
                              "conversations.json, a claude.ai export, or a generic [{'role','content'}, ...] "
                              "list). Protects the system prompt and the most recent turns verbatim.")
    parser.add_argument("--protect-recent", type=int, default=4,
                         help="Used with --session: number of most-recent turns to always keep verbatim (default: 4)")
    parser.add_argument("--target", type=float, default=None, help="Fraction of tokens to remove, e.g. 0.7 (default: 0.70, or the preset's value)")
    parser.add_argument("--content-type", choices=["auto", "code", "logs", "prose"], default="auto")
    parser.add_argument("--preset", choices=list(PRESETS), default=None, help="Named preset bundling target/dedup/floor settings")
    parser.add_argument("--model", choices=supported_models(), default="default", help="Tokenizer profile to count tokens with")
    parser.add_argument("--dedup-threshold", type=float, default=None, help="Fixed near-duplicate similarity cutoff (omit for adaptive)")
    parser.add_argument("--out", metavar="PATH", help="Write compressed text to PATH instead of stdout")
    parser.add_argument("--report", metavar="PATH", help="Write a diff report (.md or .html) to PATH")
    parser.add_argument("--quiet", action="store_true", help="Suppress the summary line printed to stderr")
    return parser


def _run_single_file(args) -> int:
    try:
        with open(args.file, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except OSError as e:
        print(f"error: could not read {args.file}: {e}", file=sys.stderr)
        return 1

    if args.preset:
        compressor = ContextCompressor.from_preset(
            args.preset,
            model=args.model,
            **({"target_compression": args.target} if args.target is not None else {}),
            **({"dedup_threshold": args.dedup_threshold} if args.dedup_threshold is not None else {}),
        )
    else:
        kwargs = dict(model=args.model)
        if args.target is not None:
            kwargs["target_compression"] = args.target
        if args.dedup_threshold is not None:
            kwargs["dedup_threshold"] = args.dedup_threshold
        compressor = ContextCompressor(**kwargs)

    report = compressor.compress(text, content_type=args.content_type)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report.compressed_text)
    else:
        print(report.compressed_text)

    if args.report:
        write_report(report, args.report, title=f"Compression report: {args.file}")
        if not args.quiet:
            print(f"report written to {args.report}", file=sys.stderr)

    if not args.quiet:
        print(report.summary(), file=sys.stderr)
    return 0


def _run_repo(args) -> int:
    from context_compressor.multifile import compress_repo

    target = args.target if args.target is not None else (
        PRESETS[args.preset].target_compression if args.preset else 0.70
    )
    report = compress_repo(args.repo, target_compression=target, model=args.model)

    if args.out:
        import os

        os.makedirs(args.out, exist_ok=True)
        for fr in report.files:
            rel = os.path.relpath(fr.path, args.repo)
            dest = os.path.join(args.out, rel)
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(fr.compressed_text)
        if not args.quiet:
            print(f"compressed files written under {args.out}", file=sys.stderr)
    else:
        for fr in report.files:
            print(f"----- {fr.path} ({fr.original_tokens} -> {fr.compressed_tokens} tokens) -----")
            print(fr.compressed_text)
            print()

    if not args.quiet:
        print(report.summary(), file=sys.stderr)
        for n in report.notes:
            print(f"  {n}", file=sys.stderr)
    return 0


def _run_diff(args) -> int:
    from context_compressor.git_diff import compress_diff

    target = args.target if args.target is not None else (
        PRESETS[args.preset].target_compression if args.preset else 0.70
    )
    repo_path = args.repo or "."

    try:
        if args.github_pr:
            from context_compressor.github_fetch import fetch_pr_diff_and_files, parse_pr_reference

            owner, repo, pr_number = parse_pr_reference(args.github_pr)
            diff_text, file_contents = fetch_pr_diff_and_files(owner, repo, pr_number)
            report = compress_diff(
                diff_text=diff_text, file_contents=file_contents, target_compression=target, model=args.model,
            )
        elif args.diff_file:
            with open(args.diff_file, "r", encoding="utf-8", errors="ignore") as f:
                diff_text = f.read()
            report = compress_diff(
                repo_path=repo_path, diff_text=diff_text, target_compression=target, model=args.model,
            )
        else:
            report = compress_diff(
                repo_path=repo_path, base_ref=args.diff, target_ref=args.diff_target_ref,
                target_compression=target, model=args.model,
            )
    except (RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if not report.files:
        print("no changed files with compressible content found", file=sys.stderr)
        return 0

    if args.out:
        import os

        os.makedirs(args.out, exist_ok=True)
        for fr in report.files:
            dest = os.path.join(args.out, fr.path)
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(fr.compressed_text)
        if not args.quiet:
            print(f"compressed files written under {args.out}", file=sys.stderr)
    else:
        for fr in report.files:
            print(f"----- {fr.path} ({fr.original_tokens} -> {fr.compressed_tokens} tokens, "
                  f"{fr.changed_blocks_kept} changed block(s) kept, "
                  f"{fr.dependency_blocks_restored} dependency block(s) restored) -----")
            print(fr.compressed_text)
            print()

    if not args.quiet:
        print(report.summary(), file=sys.stderr)
        for n in report.notes:
            print(f"  {n}", file=sys.stderr)
        if report.files_skipped:
            print(f"  skipped: {', '.join(report.files_skipped)}", file=sys.stderr)
    return 0


def _run_session(args) -> int:
    import json

    from context_compressor.session_compressor import compress_session

    try:
        with open(args.session, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        print(f"error: could not read {args.session}: {e}", file=sys.stderr)
        return 1

    target = args.target if args.target is not None else (
        PRESETS[args.preset].target_compression if args.preset else 0.70
    )

    try:
        report = compress_session(
            raw_export=raw,
            protect_recent=args.protect_recent,
            target_compression=target,
            model=args.model,
            dedup_threshold=args.dedup_threshold,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    messages = report.to_messages()
    output_json = json.dumps(messages, indent=2, ensure_ascii=False)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output_json)
    else:
        print(output_json)

    if not args.quiet:
        print(report.summary(), file=sys.stderr)
        for n in report.notes:
            print(f"  {n}", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    modes = [args.file, args.repo, args.diff, args.diff_file, args.github_pr, args.session]
    if not any(modes):
        parser.print_help()
        return 1
    if sum(1 for m in (args.file, args.repo, args.session) if m) + \
       (1 if (args.diff or args.diff_file or args.github_pr) else 0) > 1:
        print("error: pass only one of FILE, --repo DIR, --session PATH, or --diff/--diff-file/--github-pr", file=sys.stderr)
        return 1
    if args.github_pr and args.repo:
        print("error: --github-pr fetches its own file contents, don't pass --repo with it", file=sys.stderr)
        return 1

    if args.session:
        return _run_session(args)
    if args.diff or args.diff_file or args.github_pr:
        return _run_diff(args)
    if args.repo:
        return _run_repo(args)
    return _run_single_file(args)


if __name__ == "__main__":
    sys.exit(main())
