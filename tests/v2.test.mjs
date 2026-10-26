import assert from 'node:assert/strict';
import {parseMeterCSV,estimateFuel,provisionalCircuits} from '../web/v2calc.mjs';
import {readFileSync} from 'node:fs';
const project=JSON.parse(readFileSync(new URL('../app/example.json',import.meta.url)));
const cat=JSON.parse(readFileSync(new URL('../app/seed.json',import.meta.url)));

const csv=[
  'timestamp,l1_kw,l2_kw,l3_kw',
  '2026-01-01T10:00:00Z,1,2,3',
  '2026-01-01T10:30:00Z,2,2,4',
  '2026-01-01T11:00:00Z,3,4,5'
].join('\n');
const m=parseMeterCSV(csv);
assert.equal(m.samples,3);
assert.equal(m.minutes,60);
assert.equal(m.average_kw,8.5);
assert.equal(m.energy_kwh,8.5);
assert.equal(m.observed_peak_kw,12);
assert.deepEqual(m.phase_peak_kw,[3,4,5]);
assert.throws(()=>parseMeterCSV(csv.replace('l2_kw','l2_va')),/header/);
assert.throws(()=>parseMeterCSV(csv.replace('2026-01-01T10:30:00Z','2025-01-01T10:30:00Z')),/chronological/);
assert.throws(()=>parseMeterCSV(csv.replace('1,2,3','-1,2,3')),/phase kW/);

const p={...project,generator_fuel_curve:{p25:2,p50:4,p75:6,p100:8,source:'Model datasheet'}};
assert.equal(estimateFuel(p,16).status,'estimated'); // 50% of 40 kVA at 0.8 PF
assert.equal(estimateFuel(p,16).lph,4);
assert.equal(estimateFuel(p,16).litres,32);
assert.equal(estimateFuel(p,4).status,'below-25');
assert.equal(estimateFuel(p,40).status,'overload');
assert.equal(estimateFuel({...p,generator_fuel_curve:{p25:3,p50:2,p75:6,p100:8}},16).status,'non-monotonic');
const circuits=provisionalCircuits(project,cat);
assert.equal(circuits.length,6);
assert.equal(circuits[0].phase,'L1');
assert(circuits[0].estimated_a>20);
console.log('V2 measurement, fuel and circuit tests passed');
