"""Source-grounded repository graph without executing repository code.

Python uses AST scope resolution. JavaScript/TypeScript declarations and imports
are lexical hints, explicitly labeled inferred. Unsupported files remain visible.
"""
import ast
from collections import Counter
import io
import os
from pathlib import Path
import re
import subprocess
import tokenize


def build_repository_graph(directory, max_files=2000, max_symbols=10000):
    if type(max_files) is not int or not 1 <= max_files <= 10000:
        raise ValueError('Graph file limit must be between 1 and 10000.')
    if type(max_symbols) is not int or not 1 <= max_symbols <= 50000:
        raise ValueError('Graph symbol limit must be between 1 and 50000.')
    root = Path(directory).resolve()
    nodes, edges, files, trees, definitions, imports, calls = {}, set(), {}, {}, {}, [], []
    unresolved, warnings = [], []
    aliases, shadows = {}, {}

    def node(identifier, **attributes):
        nodes[identifier] = dict(id=identifier, **attributes)
        return identifier

    def edge(source, target, relation, confidence='parsed', line=None):
        if source != target or relation == 'calls':
            edges.add((source, target, relation, confidence, line or 0))

    node('module:.', name=root.name, kind='module', path='.', summary='Repository root', confidence='observed')
    paths = []
    indexed = None
    try:
        if not (root / '.git').exists():
            raise FileNotFoundError('No Git metadata at inventory root')
        git_root = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], capture_output=True, text=True, timeout=5, check=True).stdout.strip()
        if Path(git_root).resolve() == root:
            listing = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], capture_output=True, timeout=15, check=True)
            indexed = {p for p in listing.stdout.decode('utf-8', errors='replace').split('\0') if p}
    except (OSError, subprocess.SubprocessError):
        warnings.append('Git ignore rules unavailable; inventory uses generated-directory exclusions only.')
    included_dirs = {str(parent).replace(os.sep, '/') for name in (indexed or []) for parent in Path(name).parents}
    for folder, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in
                         {'.git', '.codex', '.agents', '.venv', '.cache', 'node_modules', '__pycache__', 'venv', 'dist', 'build', 'site-dist', 'vendor'})
        if indexed is not None:
            dirs[:] = [d for d in dirs if str((Path(folder) / d).relative_to(root)).replace(os.sep, '/') in included_dirs]
        for name in sorted(names):
            path = Path(folder) / name
            if indexed is not None and path.relative_to(root).as_posix() not in indexed:
                continue
            if path.is_symlink() or not path.is_file():
                continue
            paths.append(path)
            if len(paths) > max_files:
                break
        if len(paths) > max_files:
            break
    truncated = len(paths) > max_files
    for path in paths[:max_files]:
        relative = path.relative_to(root).as_posix()
        parts = Path(relative).parts[:-1]
        parent = 'module:.'
        for index in range(len(parts)):
            directory_name = '/'.join(parts[:index + 1])
            identifier = 'module:' + directory_name
            if identifier not in nodes:
                node(identifier, name=parts[index], kind='module', path=directory_name,
                     summary='Source directory', confidence='observed')
                edge(parent, identifier, 'contains', 'observed')
            parent = identifier
        fid = node('file:' + relative, name=path.name, kind='file', path=relative, line=1,
                   summary='File inventory; source semantics not parsed for this language.', confidence='observed')
        edge(parent, fid, 'contains', 'observed')
        files[relative] = fid
        if path.suffix not in {'.py', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx'}:
            continue
        try:
            if path.stat().st_size > 1000000:
                warnings.append(relative + ': source larger than 1 MB; inventory only')
                continue
            content = path.read_bytes()
            if path.suffix == '.py':
                encoding, _ = tokenize.detect_encoding(io.BytesIO(content).readline)
                tree = ast.parse(content.decode(encoding), filename=relative)
                trees[relative] = tree
                nodes[fid]['summary'] = (ast.get_docstring(tree) or 'Python module; inspect symbols and relationships.')[:400]
                nodes[fid]['confidence'] = 'parsed'
            else:
                source = content.decode('utf-8')
                # Remove comments and string contents before looking for declarations.
                masked = re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`',
                                lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), source)
                pattern = r'\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(|\bclass\s+([A-Za-z_$][\w$]*)|\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>'
                for match in re.finditer(pattern, masked):
                    if len(definitions) >= max_symbols:
                        break
                    name = next(g for g in match.groups() if g)
                    line = source.count('\n', 0, match.start()) + 1
                    sid = f'symbol:{relative}:{name}@{line}'
                    kind = 'class' if match.group(2) else 'function'
                    node(sid, name=name, kind=kind, path=relative, line=line,
                         summary='Lexically detected declaration. JavaScript/TypeScript scope and calls are not resolved.', confidence='inferred')
                    definitions[(relative, f'{name}@{line}')] = sid
                    edge(fid, sid, 'defines', 'inferred', line)
                # Dependency strings are evidence, but resolution is heuristic without a JS parser.
                for match in re.finditer(r'(?:\bfrom\s*|\brequire\s*\(\s*|\bimport\s*)[\'\"]([^\'\"]+)[\'\"]', source):
                    if not masked[match.start():match.start()+1].strip():
                        continue
                    imports.append((relative, '', match[1], [], -1, source.count('\n', 0, match.start()) + 1))
                nodes[fid]['summary'] = 'JavaScript/TypeScript: lexical declarations and import hints; no full language parser.'
        except (OSError, UnicodeError, SyntaxError, ValueError, RecursionError) as error:
            warnings.append(f'{relative}: {type(error).__name__}; inventory only')

    class Symbols(ast.NodeVisitor):
        def __init__(self, path):
            self.path, self.scope, self.owner, self.class_scope = path, '', files[path], None

        def declaration(self, item, kind):
            if len(definitions) >= max_symbols:
                return
            name = item.name if hasattr(item, 'name') else f'<lambda>@{item.lineno}'
            qualified = self.scope + '.' + name if self.scope else name
            sid = node(f'symbol:{self.path}:{qualified}@{item.lineno}', name=qualified, kind=kind,
                       path=self.path, line=item.lineno, end_line=item.end_lineno,
                       summary=((ast.get_docstring(item) if not isinstance(item, ast.Lambda) else None) or
                       f'{kind.title()} declared at {self.path}:{item.lineno}')[:400], confidence='parsed')
            definitions[(self.path, qualified)] = sid
            edge(self.owner, sid, 'defines', line=item.lineno)
            previous = self.scope, self.owner, self.class_scope
            self.scope, self.owner = qualified, sid
            if kind == 'class':
                self.class_scope = qualified
                for base in item.bases:
                    calls.append((self.path, previous[0], sid, ast.unparse(base), 'inherits', item.lineno, previous[2]))
            else:
                args = item.args
                names = {a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]}
                names.update(a.arg for a in (args.vararg, args.kwarg) if a)
                # Parameters can shadow module-level definitions or imported names.
                shadows[(self.path, qualified)] = names
            self.generic_visit(item)
            self.scope, self.owner, self.class_scope = previous

        def visit_FunctionDef(self, item): self.declaration(item, 'function')
        def visit_AsyncFunctionDef(self, item): self.declaration(item, 'function')
        def visit_ClassDef(self, item): self.declaration(item, 'class')
        def visit_Lambda(self, item): self.declaration(item, 'function')
        def visit_Import(self, item):
            for alias in item.names:
                imports.append((self.path, self.scope, alias.name, [], 0, item.lineno))
                aliases[(self.path, self.scope, alias.asname or alias.name.split('.')[0])] = (alias.name if alias.asname else alias.name.split('.')[0], '')
        def visit_ImportFrom(self, item):
            imports.append((self.path, self.scope, item.module or '', item.names, item.level, item.lineno))
        def visit_Call(self, item):
            calls.append((self.path, self.scope, self.owner, ast.unparse(item.func)[:200], 'calls', item.lineno, self.class_scope))
            self.generic_visit(item)
        def visit_Name(self, item):
            if isinstance(item.ctx, ast.Store):
                shadows.setdefault((self.path, self.scope), set()).add(item.id)

    for path, tree in trees.items():
        try:
            Symbols(path).visit(tree)
        except RecursionError:
            warnings.append(f'{path}: symbol traversal depth exceeded; graph is partial.')

    modules = {}
    packages = {}
    for path, fid in files.items():
        if not path.endswith('.py'):
            continue
        parts = path[:-3].split('/')
        if parts[0] == 'src': parts = parts[1:]
        is_package = parts[-1] == '__init__'
        module = '.'.join(parts[:-1] if is_package else parts)
        modules.setdefault(module, []).append(fid)
        packages[path] = parts[:-1]

    def target_for(module, symbol=''):
        full = module + ('.' + symbol if symbol else '')
        matches = modules.get(full, [])
        if len(matches) == 1:
            return matches[0]
        parts = full.split('.')
        for split in range(len(parts)-1, 0, -1):
            candidates = modules.get('.'.join(parts[:split]), [])
            if len(candidates) == 1:
                target = definitions.get((nodes[candidates[0]]['path'], '.'.join(parts[split:])))
                if target:
                    return target
        return None

    for path, scope, module, names, level, line in imports:
        if level == -1:
            if module.startswith('.'):
                normalized = os.path.normpath(str(Path(path).parent / module)).replace(os.sep, '/')
                candidates = [normalized] + [normalized + suffix for suffix in ('.js','.ts','.tsx','.jsx','/index.js','/index.ts')]
                match = next((files[c] for c in candidates if c in files), None)
                if match: edge(files[path], match, 'imports', 'inferred', line)
                else: unresolved.append(dict(path=path, line=line, expression=module, relation='imports'))
            else:
                external = 'external:' + module
                node(external, name=module, kind='external', path='', summary='External package import hint', confidence='inferred')
                edge(files[path], external, 'imports', 'inferred', line)
            continue
        if level:
            package = packages[path]
            if level > len(package):
                unresolved.append(dict(path=path, line=line, expression='.'*level+module, relation='imports'))
                continue
            module = '.'.join(package[:len(package)-level+1] + ([module] if module else []))
        found = target_for(module)
        if found: edge(files[path], found, 'imports', line=line)
        for alias in names:
            if alias.name == '*': continue
            aliases[(path, scope, alias.asname or alias.name)] = (module, alias.name)
            target = target_for(module, alias.name)
            if target: edge(files[path], target, 'imports', line=line)
        if not found and not any(target_for(module, n.name) for n in names):
            external = 'external:' + module
            node(external, name=module or '(relative import)', kind='external', path='', summary='Import outside the indexed files or unresolved module', confidence='parsed')
            edge(files[path], external, 'imports', line=line)

    for path, scope, owner, expression, relation, line, cls in calls:
        target, confidence = None, 'parsed'
        parts = expression.split('.')
        if not all(part.isidentifier() for part in parts):
            unresolved.append(dict(path=path, line=line, expression=expression, relation=relation)); continue
        if cls and len(parts) == 2 and parts[0] in {'self','cls'}:
            target = definitions.get((path, cls + '.' + parts[1])); confidence = 'inferred'
        else:
            current = scope
            while True:
                if cls and current == cls and scope != cls:
                    current = current.rpartition('.')[0]
                if parts[0] in shadows.get((path, current), set()):
                    break
                qualified = current + '.' + expression if current else expression
                target = definitions.get((path, qualified))
                alias = aliases.get((path, current, parts[0]))
                if not target and alias:
                    module, symbol = alias
                    suffix = '.'.join(([symbol] if symbol else []) + parts[1:])
                    target = target_for(module, suffix)
                if target or not current: break
                current = current.rpartition('.')[0]
        if target: edge(owner, target, relation, confidence, line)
        else: unresolved.append(dict(path=path, line=line, expression=expression, relation=relation))
    degree = Counter()
    for source, target, relation, confidence, line in edges:
        if relation != 'contains' and relation != 'defines': degree[source] += 1; degree[target] += 1
    for identifier, item in nodes.items():
        item['connections'] = degree[identifier]
    area_counts, file_counts = {}, {}
    for item in nodes.values():
        if item['kind'] in {'file', 'function', 'class'}:
            for parent in Path(item['path']).parents:
                key = parent.as_posix()
                area_counts.setdefault(key, Counter())[item['kind']] += 1
            file_counts.setdefault(item['path'], Counter())[item['kind']] += 1
    for item in nodes.values():
        if item['kind'] == 'module':
            area = area_counts.get(item['path'], Counter())
            item['summary'] = (f"Directory grouping {area['file']} indexed files, "
                               f"{area['function']} functions and {area['class']} classes (including subdirectories). "
                               "Open its files to inspect implementation; directory membership alone is not a runtime dependency.")
        elif item['kind'] == 'file' and file_counts.get(item['path'], {}).get('function', 0):
            item['summary'] += f" Contains {file_counts[item['path']]['function']} indexed functions and {file_counts[item['path']]['class']} classes."
    counts = Counter(n['kind'] for n in nodes.values())
    if len(definitions) >= max_symbols: warnings.append('Symbol limit reached; some declarations are not included.')
    return dict(version=1, name=root.name, nodes=list(nodes.values()),
                edges=[dict(source=s,target=t,relation=r,confidence=c,line=line) for s,t,r,c,line in sorted(edges)],
                summary=dict(files=counts['file'], modules=counts['module'], functions=counts['function'],
                             classes=counts['class'], relationships=len(edges), unresolved=len(unresolved),
                             hubs=[nodes[k]['name'] for k,_ in sorted(degree.items(), key=lambda item: (-item[1], item[0]))[:5]]),
                unresolved=unresolved[:200], unresolved_truncated=len(unresolved)>200,
                warnings=warnings, truncated=truncated, limits=dict(files=max_files,symbols=max_symbols))
