"""Bind each carrier's bundled firmware to its saved, checked watchdog build."""
from pathlib import Path
import hashlib
import json
import re

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify_watchdog(root, spec):
    folder = root / spec['root'] / 'design/watchdog_reference'
    failures = []
    result = {'status': 'FAIL', 'scope': 'Bundled source/HEX, file provenance and saved software checks; no flashing or hardware measurements.',
              'product_version': spec['version'], 'failures': failures}
    def check(condition, message):
        if not condition:
            failures.append(message)
    try:
        manifest = json.loads((folder / 'source_hashes.json').read_text('utf-8-sig'))
        proof = json.loads((folder / 'verification/software_checks.json').read_text('utf-8-sig'))
        version = (folder / 'VERSION').read_text('utf-8').strip()
        result['watchdog_version'] = version
        check(manifest.get('product_version') == spec['version'], 'Carrier version differs from watchdog integration manifest')
        check(manifest.get('watchdog_version') == version, 'Watchdog VERSION differs from manifest')
        files = manifest.get('files', {})
        check(bool(files), 'No bundled firmware file manifest')
        for name, record in files.items():
            file = (folder / name).resolve()
            check(file.is_relative_to(folder.resolve()), 'Firmware manifest path escapes bundle: ' + name)
            if not file.is_relative_to(folder.resolve()):
                continue
            check(file.is_file(), 'Missing bundled firmware file: ' + name)
            if file.is_file():
                check(file.stat().st_size == record['bytes'] and digest(file) == record['sha256'], 'Firmware file hash/size mismatch: ' + name)
        main_sha, hex_sha = digest(folder / 'main.c'), digest(folder / 'watchdog.hex')
        result.update(main_c_sha256=main_sha, hex_sha256=hex_sha, manifest_entries=len(files))
        check(proof.get('status') == 'PASS' and proof.get('fresh_rebuild_hex_matches'), 'Saved AVR build proof did not pass')
        check(main_sha == proof.get('main_c_sha256'), 'Source differs from verified AVR build')
        check(hex_sha == proof.get('hex_sha256'), 'HEX differs from verified AVR build')
        tests = proof.get('host_tests', {})
        check(tests.get('passed', 0) > 0 and tests.get('failed') == 0, 'Saved host logic tests did not pass')
        result['host_tests'] = tests
        makefile = (folder / 'Makefile').read_text('utf-8')
        for key in ('LFUSE', 'HFUSE'):
            found = re.search(r'^' + key + r'\s*\?=\s*(0x[0-9a-fA-F]+)', makefile, re.M)
            check(bool(found) and int(found[1], 16) == int(proof['fuses'][key], 16), 'Fuse profile differs from verified configuration: ' + key)
        image, base, eof = {}, 0, False
        for text in (folder / 'watchdog.hex').read_text('ascii').splitlines():
            check(not eof and text.startswith(':'), 'Malformed HEX or data after EOF')
            record = bytes.fromhex(text[1:])
            check(len(record) >= 5 and len(record) == record[0] + 5 and sum(record) % 256 == 0, 'Intel HEX record length/checksum error')
            count, address, kind = record[0], int.from_bytes(record[1:3], 'big'), record[3]
            data = record[4:4 + count]
            if kind == 0:
                for offset, byte in enumerate(data):
                    pos = base + address + offset
                    check(pos < 1024 and pos not in image, 'HEX overlap or ATtiny13A Flash overflow')
                    image[pos] = byte
            elif kind == 1:
                eof = True
            elif kind in (2, 4):
                base = int.from_bytes(data, 'big') << (4 if kind == 2 else 16)
            else:
                check(kind in (3, 5), 'Unknown Intel HEX record type')
        result['flash_bytes'] = len(image)
        check(eof and 0 in image and len(image) == proof.get('flash_bytes'), 'HEX size/reset vector differs from verified build')
        canonical = root / 'watchdog'
        if canonical.is_dir():
            for name in ('main.c', 'watchdog.hex', 'VERSION'):
                check((folder / name).read_bytes() == (canonical / name).read_bytes(), 'Carrier firmware differs from current canonical watchdog: ' + name)
            result['canonical_watchdog_checked'] = True
        else:
            result['canonical_watchdog_checked'] = False
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        failures.append(str(error))
    result['status'] = 'FAIL' if failures else 'PASS'
    return result
