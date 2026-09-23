import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { join } from 'node:path';
const { parseRoute, routeHref, homeRoute, canOpenRoute, PROFILE_PAGES } = await import(pathToFileURL(join(process.env.CQ_TEST_BUILD, 'navigation.mjs')));
const account = role => ({ role, employee_id: ['hr', 'client'].includes(role) ? null : 'E0028' });

test('workspace and selected employee routes round-trip as genuine hash links', () => {
    for (const page of ['team', 'catalog', 'skill-catalog', 'imports', 'accounts', 'account']) {
        const route = { page }; assert.deepEqual(parseRoute(routeHref(route)), route);
    }
    for (const page of PROFILE_PAGES) {
        const route = { page, employeeId: 'E0028' };
        assert.equal(routeHref(route), `#/employees/E0028/${page}`);
        assert.deepEqual(parseRoute(routeHref(route)), route);
    }
});

test('unknown, malformed and unsafe employee paths fall back without throwing', () => {
    for (const hash of ['', '#/', '#workspace', '#/hr', '#/catalog/extra', '#/employees/E0028', '#/employees/%E0%A4%A/skills', '#/employees/a%2Fb/profile', '#/employees/../profile', '#/employees//profile', '#/employees/E0028/unknown']) assert.equal(parseRoute(hash), null, hash);
});

test('each role has a useful home and only appropriate route families', () => {
    assert.deepEqual(homeRoute(account('hr')), { page: 'team' });
    assert.deepEqual(homeRoute(account('client')), { page: 'account' });
    for (const role of ['employee', 'operator', 'manager', 'supervisor']) assert.deepEqual(homeRoute(account(role)), { page: 'profile', employeeId: 'E0028' });
    for (const role of ['employee', 'operator', 'manager', 'supervisor', 'client', 'hr']) {
        const who = account(role);
        assert.equal(canOpenRoute(who, { page: 'account' }), true);
        assert.equal(canOpenRoute(who, { page: 'team' }), ['hr', 'manager', 'supervisor'].includes(role));
        for (const page of ['catalog', 'skill-catalog', 'imports', 'accounts']) assert.equal(canOpenRoute(who, { page }), role === 'hr');
        assert.equal(canOpenRoute(who, { page: 'history', employeeId: 'E0028' }), role !== 'client');
        assert.equal(canOpenRoute(who, { page: 'history', employeeId: 'OTHER' }), ['hr', 'manager', 'supervisor'].includes(role));
    }
});
