const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8');
const render = vm.runInNewContext(source.slice(0, source.indexOf('async function accounts()')) +
  '\n({objectResultsHtml, stateObjectsHtml, displayName, relevant, removalSummaryHtml});', {document: {getElementById() {}}});

test('change display preserves measured categories and prioritizes missing objects', () => {
  const html = render.objectResultsHtml([
    {object_id:'a',label:'Bottle',status:'ADDED'},
    {object_id:'m',label:'Mouse',status:'POSSIBLY_MISSING'},
    {object_id:'r',label:'Can',status:'REMOVED'},
    {object_id:'u',label:'Laptop',status:'UNCERTAIN'},
  ]);
  assert.ok(html.indexOf('Removed') < html.indexOf('Possibly Missing'));
  assert.ok(html.indexOf('Possibly Missing') < html.indexOf('Added'));
  assert.match(html, /Needs review/);
  assert.doesNotMatch(html, /Laptop|confidence|object_id/);
});

test('unchanged is not relabeled as a confirmed change', () => {
  const html = render.objectResultsHtml([{object_id:'l',label:'Laptop',status:'UNCHANGED'}]);
  assert.match(html, /Matched in both scans/);
  assert.doesNotMatch(html, /Confirmed change/);
});

test('uncertain candidate is not shown as verified present or tracked', () => {
  const html = render.stateObjectsHtml([{stable_id:'private-uuid',label:'laptop computer',status:'UNKNOWN',
    presence:'UNKNOWN',last_seen:'2026-10-11T21:30:00Z',enrollment_status:'NOT_ENROLLED'}]);
  assert.match(html, /Laptop|Needs Review|Candidate/);
  assert.doesNotMatch(html, /private-uuid|>Present<|Tracked object|confidence/);
});

test('object labels remain escaped and presentation-only', () => {
  const html = render.stateObjectsHtml([{label:'<script>bad</script>',status:'POSSIBLY_MISSING',
    last_seen:null,enrollment_status:'CONFIRMED'}]);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
});

test('Product View uses enrollment and accepted states, not confidence', () => {
  assert.equal(render.relevant({status:'UNKNOWN',confidence:.99}),false);
  assert.equal(render.relevant({status:'UNKNOWN',enrollment_status:'CONFIRMED',confidence:.42}),true);
  assert.equal(render.relevant({status:'UNCHANGED',confidence:.32}),true);
  assert.equal(render.relevant({status:'UNCHANGED',ignored:true}),false);
});

test('confirmed needs-review names are visible without upgrading certainty', () => {
  const html=render.objectResultsHtml([{object_id:'b',label:'Backpack',status:'UNCERTAIN',enrollment_status:'CONFIRMED'}]);
  assert.match(html,/Backpack|Needs Review/);
  assert.doesNotMatch(html,/Confirmed change|Verified absence/);
});

test('missing summary is expandable, named and never claims confirmed removal or a percentage', () => {
  const items=['Plate','Sandwich'].map(label=>({label,status:'POSSIBLY_MISSING'}));
  assert.match(render.removalSummaryHtml(items),/Two Possibly Removed|Not a confirmed removal/);
  const detail=render.removalSummaryHtml(items,true);
  assert.match(detail,/<details|<summary|Plate|Sandwich|Needs review/);
  assert.doesNotMatch(detail,/Verified absence|%/);
  assert.equal(render.displayName('Fabric Clothing'),'Fabric Clothing');
  assert.equal(render.displayName('Backpack'),'Backpack');
});
