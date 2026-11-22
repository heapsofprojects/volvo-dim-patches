// SPDX-License-Identifier: GPL-3.0-or-later
// Core of the online patch tool. Runs entirely in the browser (and in Node
// for testing): the flash dump is never sent anywhere.
(function (root) {
  "use strict";

  function hexToBytes(hex) {
    var out = new Uint8Array(hex.length / 2);
    for (var i = 0; i < out.length; i++) {
      out[i] = parseInt(hex.substr(i * 2, 2), 16);
    }
    return out;
  }

  function bytesToHex(bytes) {
    var s = "";
    for (var i = 0; i < bytes.length; i++) {
      s += (bytes[i] < 16 ? "0" : "") + bytes[i].toString(16);
    }
    return s;
  }

  async function sha256Hex(bytes) {
    var digest = await root.crypto.subtle.digest("SHA-256", bytes);
    return bytesToHex(new Uint8Array(digest));
  }

  // Which patches fit this dump? Matching is by SHA-256 of the whole image.
  async function identify(patches, bytes) {
    var sha = await sha256Hex(bytes);
    var result = { sha256: sha, size: bytes.length, applicable: [], alreadyPatched: [] };
    patches.forEach(function (p) {
      if (p.stock_sha256 === sha) result.applicable.push(p);
      if (p.patched_sha256 === sha || p.as_flashed_sha256 === sha) result.alreadyPatched.push(p);
    });
    return result;
  }

  // Returns a new Uint8Array; throws Error with a readable message on any
  // mismatch. The input is never modified.
  async function applyPatch(patch, bytes) {
    if (bytes.length !== patch.image_size) {
      throw new Error("File is " + bytes.length + " bytes, expected " + patch.image_size + ".");
    }
    if ((await sha256Hex(bytes)) !== patch.stock_sha256) {
      throw new Error("This file is not the stock image this patch was written for.");
    }
    var out = new Uint8Array(bytes);
    patch.ops.forEach(function (op) {
      var off = parseInt(op.offset, 16);
      var neu = hexToBytes(op.write);
      var i;
      if (op.expect.indexOf("ff*") === 0) {
        for (i = 0; i < neu.length; i++) {
          if (out[off + i] !== 0xff) throw new Error("Flash at " + op.offset + " is not empty.");
        }
      } else {
        var exp = hexToBytes(op.expect);
        for (i = 0; i < exp.length; i++) {
          if (out[off + i] !== exp[i]) throw new Error("Unexpected bytes at " + op.offset + ".");
        }
      }
      out.set(neu, off);
    });
    if ((await sha256Hex(out)) !== patch.patched_sha256) {
      throw new Error("Internal error: result checksum mismatch. Nothing to download.");
    }
    return out;
  }

  function bytesChanged(patch) {
    return patch.ops.reduce(function (n, op) { return n + op.write.length / 2; }, 0);
  }

  var api = { identify: identify, applyPatch: applyPatch, sha256Hex: sha256Hex, bytesChanged: bytesChanged };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.DimPatcher = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
