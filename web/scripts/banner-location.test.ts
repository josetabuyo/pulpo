import { test } from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_BANNER_LOCATION } from "../lib/business/chats";

// Bug real 2026-08-26: el default apuntaba a Lugano, SUIZA (mismo nombre,
// ciudad equivocada) -- Rodolfo (cliente Luganense, Buenos Aires) reportó
// hora "descontrolada" y 28°C en pleno invierno porteño en el chat, que
// corre sobre este default (chat_configs.info_banner no tiene location
// propia seteada). Ver web/lib/business/chats.ts.
test("DEFAULT_BANNER_LOCATION apunta a Villa Lugano, Buenos Aires (no a Lugano, Suiza)", () => {
  assert.equal(DEFAULT_BANNER_LOCATION.timezone, "America/Argentina/Buenos_Aires");
  // Hemisferio sur: latitud negativa. El bug original tenía lat +46 (Suiza).
  assert.ok(DEFAULT_BANNER_LOCATION.lat < 0, "latitud debe ser negativa (hemisferio sur)");
  // Buenos Aires: longitud oeste, entre -59 y -58.
  assert.ok(
    DEFAULT_BANNER_LOCATION.lon > -59 && DEFAULT_BANNER_LOCATION.lon < -58,
    "longitud debe caer en el rango de CABA",
  );
});
