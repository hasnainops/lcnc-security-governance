const test = require('node:test');
const assert = require('node:assert/strict');
const {catalog, validate, view} = require('../governance-portal/platform-overview.js');
const fixture = () => ({schema_version: 1, source: 'docker_compose', observation_status: 'current',
  observed_at: '2026-10-19T08:55:44+00:00', age_seconds: 1, stale_after_seconds: 30,
  services: catalog.map(([service], i) => ({service, container_count: 1, container_state: 'running',
    docker_health: i < 14 ? 'healthy' : 'not_configured', observation_status: 'current'}))});

test('running, healthy and unconfigured checks remain distinct', () => {
  assert.deepEqual(view(validate(fixture())).counts, [20,14,6,0]);
});
test('browser ages current data without a new response and withholds counts', () => {
  const data = validate(fixture());
  assert.equal(view(data,29).status, 'current');
  const stale = view(data,30);
  assert.equal(stale.status, 'stale');
  assert.deepEqual(stale.counts, [null,null,null,null]);
  assert.equal(stale.services[0].state,'running');
});
test('unavailable and failed reads never retain healthy service values', () => {
  const data = fixture(); data.observation_status = 'unavailable';
  assert.equal(view(data).services[0].health,'unknown');
  assert.equal(view(null).services.length,20);
  assert.deepEqual(view(null).counts,[null,null,null,null]);
});
test('exited container with historical healthy status does not count as healthy', () => {
  const data = fixture(); data.services[0].container_state='exited';
  assert.deepEqual(view(validate(data)).counts,[19,13,6,0]);
});
test('catalog drift, duplicates, invalid ages and mismatched row status are rejected', () => {
  for (const mutate of [
    d=>d.services.pop(), d=>d.services[0].service='unexpected',
    d=>d.services[0].service=d.services[1].service,
    d=>d.age_seconds=-1, d=>d.age_seconds=null, d=>d.age_seconds=NaN,
    d=>d.observed_at='invalid', d=>d.services[0].observation_status='stale',
    d=>d.services[0].container_count=null
  ]) { const data=fixture(); mutate(data); assert.throws(()=>validate(data)); }
});
test('catalog matches the collector service catalog', () => {
  const fs=require('node:fs'); const path=require('node:path');
  const source=fs.readFileSync(path.join(__dirname,'../governance-api/app/platform_status.py'),'utf8');
  const block=source.split('SERVICES = (')[1].split(')')[0];
  const names=[...block.matchAll(/"([a-z-]+)"/g)].map(match=>match[1]);
  assert.deepEqual(catalog.map(([name])=>name),names);
});
