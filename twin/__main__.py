import argparse
import json
import logging
from .pipeline import prepare, diagnose
from .export import load_tables


def main():
    parser = argparse.ArgumentParser(description='BDG2 — jumeau énergétique de démonstration')
    parser.add_argument('--config', default='config.json')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('prepare')
    sub.add_parser('diagnose')
    loader = sub.add_parser('load')
    loader.add_argument('--dry-run', action='store_true')
    loader.add_argument('--batch-size', type=int, default=500)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    config = json.load(open(args.config))
    if args.command == 'prepare': prepare(config)
    elif args.command == 'diagnose': diagnose(config)
    else: load_tables(config['output'], args.batch_size, args.dry_run)


if __name__ == '__main__':
    main()
