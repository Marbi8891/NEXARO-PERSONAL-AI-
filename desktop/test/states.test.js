"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { StateMachine, STATES: S, canTransition, InvalidTransitionError, TRANSITIONS } = require("../src/main/states");

test("estados: el camino feliz llega a READY", () => {
  const m = new StateMachine();
  for (const s of [S.CHECKING_DEPENDENCIES, S.DOCKER_STARTING, S.SERVICES_STARTING, S.HEALTH_CHECKS, S.READY]) m.transition(s);
  assert.equal(m.state, S.READY);
  assert.deepEqual(m.history, [S.INITIALIZING, S.CHECKING_DEPENDENCIES, S.DOCKER_STARTING, S.SERVICES_STARTING, S.HEALTH_CHECKS, S.READY]);
});

test("estados: están los diez estados del enunciado", () => {
  assert.deepEqual(Object.keys(S).sort(), ["CHECKING_DEPENDENCIES", "DEGRADED", "DOCKER_STARTING", "ERROR", "HEALTH_CHECKS", "INITIALIZING", "READY", "SERVICES_STARTING", "STOPPED", "STOPPING"]);
  assert.deepEqual(Object.keys(TRANSITIONS).sort(), Object.keys(S).sort());
});

test("estados: transiciones no válidas lanzan", () => {
  const m = new StateMachine();
  assert.throws(() => m.transition(S.READY), InvalidTransitionError);
  assert.throws(() => m.transition("NOPE"), InvalidTransitionError);
  assert.equal(m.state, S.INITIALIZING);
});

test("estados: ERROR y STOPPING alcanzables desde cualquier estado activo", () => {
  for (const from of [S.INITIALIZING, S.CHECKING_DEPENDENCIES, S.DOCKER_STARTING, S.SERVICES_STARTING, S.HEALTH_CHECKS, S.READY, S.DEGRADED]) {
    assert.ok(canTransition(from, S.ERROR), `${from} → ERROR`);
    assert.ok(canTransition(from, S.STOPPING), `${from} → STOPPING`);
  }
  assert.ok(canTransition(S.ERROR, S.STOPPING));
  assert.ok(!canTransition(S.ERROR, S.ERROR));
  assert.ok(!canTransition(S.STOPPED, S.ERROR));
  assert.ok(!canTransition(S.STOPPED, S.STOPPING));
  assert.ok(!canTransition(S.STOPPING, S.STOPPING));
  assert.ok(!canTransition(S.STOPPING, S.READY));
});

test("estados: ERROR guarda código, reintentar limpia las comprobaciones", () => {
  const m = new StateMachine();
  m.transition(S.CHECKING_DEPENDENCIES);
  m.setCheck("docker", "fail", "No instalado");
  m.transition(S.ERROR, { errorCode: "DOCKER_NOT_INSTALLED" });
  assert.equal(m.snapshot().errorCode, "DOCKER_NOT_INSTALLED");
  m.transition(S.INITIALIZING);
  assert.deepEqual(m.snapshot().checks, {});
  assert.equal(m.snapshot().errorCode, null);
});

test("estados: emite change con estado anterior y la instantánea es una copia", () => {
  const m = new StateMachine();
  const seen = [];
  m.on("change", (snap, from) => seen.push([from, snap.state]));
  m.transition(S.CHECKING_DEPENDENCIES);
  m.setCheck("windows", "ok", "Windows 11");
  assert.deepEqual(seen, [[S.INITIALIZING, S.CHECKING_DEPENDENCIES], [S.CHECKING_DEPENDENCIES, S.CHECKING_DEPENDENCIES]]);
  const snap = m.snapshot();
  snap.checks.windows.status = "fail";
  assert.equal(m.snapshot().checks.windows.status, "ok");
  assert.throws(() => m.setCheck("x", "bogus"), TypeError);
});
