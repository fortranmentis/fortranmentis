#!/usr/bin/env python3
"""Refresh aggregate language cards using an authenticated GitHub CLI session.

Run from a trusted local machine with access to all of your owned repositories:
    python3 scripts/update-language-stats.py --owner fortranmentis

Only aggregate language counts are written. No token, repository inventory,
private repository names, paths, or source contents are included in the output.
"""

import argparse
from collections import Counter
from datetime import datetime, date
from html import escape
import json
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo


def api(endpoint, paginate=False):
    command = ['gh', 'api']
    if paginate:
        command += ['--paginate', '--slurp']
    command.append(endpoint)
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def render_card(languages, total, updated):
    ranked = sorted(languages.items(), key=lambda item: (-item[1], item[0]))
    visible = ranked[:6]
    remainder = sum(count for _, count in ranked[6:])
    if remainder:
        visible.append(('Other', remainder))
    colors = {
        'Rust': '#DEA584', 'Kotlin': '#A97BFF', 'Swift': '#F59076',
        'TypeScript': '#64A6ED', 'Python': '#F4D35E', 'CSS': '#B692E5',
        'JavaScript': '#F1E05A', 'HTML': '#E8846B', 'Shell': '#89D887',
        'Other': '#8DAAC4',
    }
    rows = (len(visible) + 1) // 2
    height = max(170, 94 + (rows-1)*20 + 16)
    description = '; '.join(f'{name}: {count/total*100:.4f}%' for name, count in ranked)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="440" height="{height}" viewBox="0 0 440 {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Code language composition: public and private repositories</title>',
        f'<desc id="desc">Snapshot {updated}. Owned, non-fork repositories; profile repository excluded. GitHub language byte counts. {escape(description)}. Other combines languages outside the top six.</desc>',
        f'<rect x=".5" y=".5" width="439" height="{height-1}" rx="14" fill="#0A172B" stroke="#23445C"/>',
        '<g font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Arial, sans-serif">',
        '<text x="25" y="29" fill="#5EEAD4" font-size="18" font-weight="600">Code Languages</text>',
        f'<text x="25" y="47" fill="#9DB6CB" font-size="11">Public + private · {updated}</text>',
        '<defs><clipPath id="bar"><rect x="25" y="59" width="390" height="8" rx="4"/></clipPath></defs>',
        '<g clip-path="url(#bar)">',
    ]
    x = 25.0
    for name, count in visible:
        width = count / total * 390
        parts.append(f'<rect x="{x:.6f}" y="59" width="{width:.6f}" height="8" fill="{colors.get(name, "#8DAAC4")}"/>')
        x += width
    parts.append('</g>')
    for index, (name, count) in enumerate(visible):
        x = 25 if index % 2 == 0 else 225
        y = 92 + (index // 2)*20
        parts += [
            f'<circle cx="{x+5}" cy="{y-4}" r="4.5" fill="{colors.get(name, "#8DAAC4")}"/>',
            f'<text x="{x+17}" y="{y}" fill="#CEE0EC" font-size="12">{escape(name)} {count/total*100:.2f}%</text>',
        ]
    parts += ['</g>', '</svg>']
    return '\n'.join(parts)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner', default='fortranmentis')
    parser.add_argument('--date', help='Snapshot date (YYYY-MM-DD); defaults to today in Asia/Seoul')
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parents[1]/'assets')
    args = parser.parse_args()
    updated = date.fromisoformat(args.date).isoformat() if args.date else datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    user = api('user')
    if user['login'].casefold() != args.owner.casefold():
        raise SystemExit('Authenticate gh as the repository owner before refreshing private-language statistics.')
    pages = api('user/repos?affiliation=owner&visibility=all&per_page=100&sort=full_name', paginate=True)
    owned = [repo for page in pages for repo in page if repo['owner']['login'].casefold() == args.owner.casefold()]
    expected_private = user.get('owned_private_repos')
    if isinstance(expected_private, int) and sum(bool(repo['private']) for repo in owned) != expected_private:
        raise SystemExit('Private repository coverage is incomplete; keep the existing snapshot.')
    selected = [repo for repo in owned if not repo['fork'] and repo['name'].casefold() != args.owner.casefold()]
    if not any(repo['private'] for repo in selected):
        raise SystemExit('No private repositories are visible; keep the existing snapshot.')
    totals = Counter()
    for repo in selected:
        # Fail the refresh if any repository is unavailable; never publish partial totals.
        counts = api(f'repos/{repo["full_name"]}/languages')
        if not isinstance(counts, dict) or any(not isinstance(v, int) or v < 0 for v in counts.values()):
            raise SystemExit('Invalid language metadata; keep the existing snapshot.')
        totals.update({name: count for name, count in counts.items() if count})
    total = sum(totals.values())
    if not total:
        raise SystemExit('No language bytes were returned; keep the existing snapshot.')
    languages = dict(sorted(totals.items(), key=lambda item: (-item[1], item[0])))
    # These aggregate fields are the only material written to public artifacts.
    data = {
        'updated_on': updated,
        'unit': 'GitHub repository language bytes',
        'scope': 'Accessible owner-owned public and private non-fork repositories; profile repository excluded; archived repositories included',
        'total_bytes': total,
        'languages': languages,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir/'language-stats.json').write_text(json.dumps(data, indent=2)+'\n')
    (args.output_dir/'language-stats.svg').write_text(render_card(languages, total, updated))
    print(f'Updated aggregate language card ({updated}); private repository identities were not exported.')


if __name__ == '__main__':
    main()
