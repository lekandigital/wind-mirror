"""Print the drag-area time series of a simulated clip."""
import sys, json
R = sorted([json.loads(l) for l in open(sys.argv[1])], key=lambda r: r['k'])
print(' '.join('%.1fs:%.2f' % (r['t'], r['CdA']) for r in R))
c = [r['CdA'] for r in R]
print('n', len(R), 'min %.3f max %.3f' % (min(c), max(c)), 'median seconds per run %.1f' % sorted(r['seconds'] for r in R)[len(R) // 2])
