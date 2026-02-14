// ExportDecompJsonl.java  –  analyzer_ghidra_decompile v1
//
// Rich per-function extraction for the two-tier pipeline.
// Emits one compact JSON line per function, plus a trailing summary record.
//
// Args: <out_jsonl_path>
//
// Requires Ghidra >= 11.0, Gson on classpath (ships with Ghidra).
//
// The Python worker (analyzer_ghidra_decompile) consumes this output
// and applies schema validation, policy verdicts, noise classification,
// and proxy metrics.

import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.framework.Application;
import ghidra.program.model.address.*;
import ghidra.program.model.block.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.lang.Register;
import ghidra.program.model.pcode.*;
import ghidra.program.model.symbol.*;

import com.google.gson.*;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class ExportDecompJsonl extends GhidraScript {

    private Gson gson;

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            println("Usage: ExportDecompJsonl.java <out_jsonl_path>");
            return;
        }
        String outPath = args[0];

        // Compact, stable-key JSON via Gson
        gson = new GsonBuilder()
            .disableHtmlEscaping()
            .create();

        // ── Decompiler setup ─────────────────────────────────────────
        DecompInterface ifc = new DecompInterface();
        ifc.openProgram(currentProgram);

        // ── Output file ──────────────────────────────────────────────
        File outFile = new File(outPath);
        outFile.getParentFile().mkdirs();

        int totalFunctions = 0;
        int decompileOk = 0;
        int decompileFail = 0;

        try (BufferedWriter w = new BufferedWriter(
                new OutputStreamWriter(new FileOutputStream(outFile), StandardCharsets.UTF_8))) {

            FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);

            while (it.hasNext() && !monitor.isCancelled()) {
                Function f = it.next();
                totalFunctions++;

                JsonObject rec = new JsonObject();
                rec.addProperty("_type", "function");

                // ── Metadata ─────────────────────────────────────────
                Address entry = f.getEntryPoint();
                String entryHex = "0x" + entry.toString().toLowerCase();
                rec.addProperty("entry_hex", entryHex);
                rec.addProperty("entry_va", entry.getOffset());
                rec.addProperty("name", f.getName());

                String ns = f.getParentNamespace().getName();
                if ("Global".equals(ns)) {
                    rec.add("namespace", JsonNull.INSTANCE);
                } else {
                    rec.addProperty("namespace", ns);
                }

                // Section / memory block hint (needed for is_external_block too)
                MemoryBlock mb = currentProgram.getMemory().getBlock(entry);

                // is_external_block: true if Ghidra API says external OR function
                // resides in the EXTERNAL memory block (import stubs).
                boolean isExternal = f.isExternal()
                    || (mb != null && "EXTERNAL".equals(mb.getName()));
                rec.addProperty("is_external_block", isExternal);
                rec.addProperty("is_thunk", f.isThunk());

                // Body range
                AddressSetView body = f.getBody();
                if (body != null && !body.isEmpty()) {
                    rec.addProperty("body_start_va", body.getMinAddress().getOffset());
                    rec.addProperty("body_end_va", body.getMaxAddress().getOffset());
                    rec.addProperty("size_bytes", body.getNumAddresses());
                } else {
                    rec.add("body_start_va", JsonNull.INSTANCE);
                    rec.add("body_end_va", JsonNull.INSTANCE);
                    rec.add("size_bytes", JsonNull.INSTANCE);
                }

                // Section hint output
                if (mb != null) {
                    rec.addProperty("section_hint", mb.getName());
                } else {
                    rec.add("section_hint", JsonNull.INSTANCE);
                }

                // Is import (external + thunk OR in EXTERNAL block)
                // Note: isImport uses the same logic as isExternal above.
                rec.addProperty("is_import", isExternal);

                // ── Instruction count ────────────────────────────────
                int insnCount = 0;
                if (body != null && !body.isEmpty()) {
                    InstructionIterator insns =
                        currentProgram.getListing().getInstructions(body, true);
                    while (insns.hasNext()) {
                        insns.next();
                        insnCount++;
                    }
                }
                rec.addProperty("insn_count", insnCount);

                // ── Decompilation ────────────────────────────────────
                String cRaw = null;
                String error = null;
                JsonArray warningsRaw = new JsonArray();
                HighFunction highFunc = null;

                try {
                    DecompileResults res = ifc.decompileFunction(f, 30, monitor);
                    if (res != null && res.decompileCompleted()
                            && res.getDecompiledFunction() != null) {
                        cRaw = res.getDecompiledFunction().getC();
                        highFunc = res.getHighFunction();
                        decompileOk++;
                    } else {
                        error = (res == null) ? "null_results"
                            : (res.getErrorMessage() != null ? res.getErrorMessage() : "unknown");
                        decompileFail++;
                    }
                    // Collect warnings from decompiler messages
                    if (res != null && res.getErrorMessage() != null
                            && !res.getErrorMessage().isEmpty()
                            && cRaw != null) {
                        // Decompile succeeded but had warnings
                        for (String line : res.getErrorMessage().split("\\n")) {
                            String trimmed = line.trim();
                            if (!trimmed.isEmpty()) {
                                warningsRaw.add(trimmed);
                            }
                        }
                    }
                } catch (Exception ex) {
                    error = ex.getClass().getSimpleName() + ": " + ex.getMessage();
                    decompileFail++;
                }

                if (cRaw != null) {
                    rec.addProperty("c_raw", cRaw);
                } else {
                    rec.add("c_raw", JsonNull.INSTANCE);
                }

                if (error != null) {
                    rec.addProperty("error", error);
                } else {
                    rec.add("error", JsonNull.INSTANCE);
                }

                rec.add("warnings_raw", warningsRaw);

                // ── Variables from HighFunction ──────────────────────
                JsonArray varsArr = new JsonArray();
                if (highFunc != null) {
                    try {
                        LocalSymbolMap lsm = highFunc.getLocalSymbolMap();
                        Iterator<HighSymbol> symIter = lsm.getSymbols();
                        while (symIter.hasNext()) {
                            HighSymbol sym = symIter.next();
                            JsonObject v = buildVarRecord(sym);
                            varsArr.add(v);
                        }
                    } catch (Exception ex) {
                        // If variable extraction fails, continue
                    }
                }
                rec.add("variables", varsArr);

                // ── CFG via BasicBlockModel ──────────────────────────
                JsonArray blocksArr = new JsonArray();
                if (body != null && !body.isEmpty()) {
                    try {
                        BasicBlockModel bbModel = new BasicBlockModel(currentProgram);
                        CodeBlockIterator blockIter =
                            bbModel.getCodeBlocksContaining(body, monitor);
                        int blockIdx = 0;
                        while (blockIter.hasNext()) {
                            CodeBlock block = blockIter.next();
                            JsonObject blk = new JsonObject();
                            blk.addProperty("block_id", blockIdx);
                            blk.addProperty("start_va",
                                block.getMinAddress().getOffset());
                            blk.addProperty("end_va",
                                block.getMaxAddress().getOffset());

                            JsonArray succs = new JsonArray();
                            CodeBlockReferenceIterator destIter =
                                block.getDestinations(monitor);
                            while (destIter.hasNext()) {
                                CodeBlockReference ref = destIter.next();
                                CodeBlock destBlock = ref.getDestinationBlock();
                                // Only include successors within this function
                                if (destBlock != null && body.contains(
                                        destBlock.getMinAddress())) {
                                    succs.add(destBlock.getMinAddress().getOffset());
                                }
                            }
                            blk.add("succ_va", succs);
                            blocksArr.add(blk);
                            blockIdx++;
                        }
                    } catch (Exception ex) {
                        // CFG extraction failed; emit empty blocks
                    }
                }
                rec.add("blocks", blocksArr);

                // ── Callsites ────────────────────────────────────────
                JsonArray callsArr = new JsonArray();
                if (body != null && !body.isEmpty()) {
                    try {
                        if (highFunc != null) {
                            Iterator<PcodeOpAST> ops = highFunc.getPcodeOps();
                            while (ops.hasNext()) {
                                PcodeOpAST op = ops.next();
                                int opcode = op.getOpcode();
                                if (opcode == PcodeOp.CALL
                                        || opcode == PcodeOp.CALLIND) {
                                    JsonObject call = new JsonObject();
                                    Address siteAddr = op.getSeqnum().getTarget();
                                    call.addProperty("callsite_va",
                                        siteAddr.getOffset());
                                    call.addProperty("callsite_hex",
                                        "0x" + siteAddr.toString().toLowerCase());

                                    boolean isDirect = (opcode == PcodeOp.CALL);
                                    call.addProperty("call_kind",
                                        isDirect ? "DIRECT" : "INDIRECT");

                                    if (isDirect) {
                                        Varnode target = op.getInput(0);
                                        Address calleeAddr = target.getAddress();
                                        Function callee =
                                            currentProgram.getFunctionManager()
                                                .getFunctionAt(calleeAddr);
                                        if (callee != null) {
                                            call.addProperty("callee_entry_va",
                                                calleeAddr.getOffset());
                                            call.addProperty("callee_name",
                                                callee.getName());
                                            call.addProperty(
                                                "is_external_target",
                                                callee.isExternal());
                                            call.addProperty(
                                                "is_import_proxy_target",
                                                callee.isExternal()
                                                    || callee.isThunk());
                                        } else {
                                            call.addProperty("callee_entry_va",
                                                calleeAddr.getOffset());
                                            call.add("callee_name",
                                                JsonNull.INSTANCE);
                                            call.addProperty(
                                                "is_external_target", false);
                                            call.addProperty(
                                                "is_import_proxy_target", false);
                                        }
                                    } else {
                                        call.add("callee_entry_va",
                                            JsonNull.INSTANCE);
                                        call.add("callee_name",
                                            JsonNull.INSTANCE);
                                        call.addProperty(
                                            "is_external_target", false);
                                        call.addProperty(
                                            "is_import_proxy_target", false);
                                    }

                                    callsArr.add(call);
                                }
                            }
                        }
                    } catch (Exception ex) {
                        // Callsite extraction failed
                    }
                }
                rec.add("calls", callsArr);

                // Emit the record as one compact JSON line
                w.write(gson.toJson(rec));
                w.newLine();
            }

            // ── Summary trailer record ───────────────────────────────
            JsonObject summary = new JsonObject();
            summary.addProperty("_type", "summary");
            summary.addProperty("ghidra_version",
                Application.getApplicationVersion());
            summary.addProperty("java_version",
                System.getProperty("java.version"));
            summary.addProperty("program_name",
                currentProgram.getName());
            summary.addProperty("program_arch",
                currentProgram.getLanguage().getProcessor().toString());
            summary.addProperty("total_functions", totalFunctions);
            summary.addProperty("decompile_ok", decompileOk);
            summary.addProperty("decompile_fail", decompileFail);
            summary.addProperty("analysis_options", "default");

            // Image base — critical for PIE (ET_DYN) rebase correction.
            // Ghidra loads PIE binaries at 0x100000 by default; this lets
            // downstream consumers normalise addresses back to ELF VAs.
            summary.addProperty("image_base",
                currentProgram.getImageBase().getOffset());

            w.write(gson.toJson(summary));
            w.newLine();

        } finally {
            ifc.dispose();
        }

        println("Wrote " + totalFunctions + " functions + summary to: " + outPath);
    }

    // ── Variable record helper ───────────────────────────────────────

    private JsonObject buildVarRecord(HighSymbol sym) {
        JsonObject v = new JsonObject();

        v.addProperty("name", sym.getName());
        v.addProperty("is_param", sym.isParameter());
        v.addProperty("size_bytes", sym.getSize());

        // Data type
        if (sym.getDataType() != null) {
            v.addProperty("type_str", sym.getDataType().getDisplayName());
        } else {
            v.add("type_str", JsonNull.INSTANCE);
        }

        // Storage analysis
        HighVariable hv = sym.getHighVariable();
        VariableStorage storage = sym.getStorage();

        String storageClass = "UNKNOWN";
        String storageKey = "unk:" + sym.getName();
        Long stackOffset = null;
        String registerName = null;
        Long addrVa = null;

        if (storage != null) {
            if (storage.isStackStorage()) {
                storageClass = "STACK";
                stackOffset = (long) storage.getStackOffset();
                String sign = stackOffset >= 0 ? "+" : "-";
                storageKey = "stack:off:" + sign + "0x"
                    + Long.toHexString(Math.abs(stackOffset));
            } else if (storage.isRegisterStorage()) {
                storageClass = "REGISTER";
                Register reg = storage.getRegister();
                if (reg != null) {
                    registerName = reg.getName();
                    storageKey = "reg:" + registerName;
                }
            } else if (storage.isMemoryStorage()) {
                storageClass = "MEMORY";
                Address addr = storage.getMinAddress();
                if (addr != null) {
                    addrVa = addr.getOffset();
                    storageKey = "mem:0x" + Long.toHexString(addrVa);
                }
            } else if (storage.isUniqueStorage()) {
                storageClass = "UNIQUE";
                storageKey = "uniq:" + sym.getName();
            }
        }

        v.addProperty("storage_class", storageClass);
        v.addProperty("storage_key", storageKey);

        if (stackOffset != null) {
            v.addProperty("stack_offset", stackOffset);
        } else {
            v.add("stack_offset", JsonNull.INSTANCE);
        }
        if (registerName != null) {
            v.addProperty("register_name", registerName);
        } else {
            v.add("register_name", JsonNull.INSTANCE);
        }
        if (addrVa != null) {
            v.addProperty("addr_va", addrVa);
        } else {
            v.add("addr_va", JsonNull.INSTANCE);
        }

        // Access sites: instruction addresses from varnode instances
        JsonArray accessSites = new JsonArray();
        boolean truncated = false;
        if (hv != null) {
            try {
                Varnode[] instances = hv.getInstances();
                Set<Long> seenAddrs = new TreeSet<>();
                for (Varnode vn : instances) {
                    PcodeOp def = vn.getDef();
                    if (def != null) {
                        Address a = def.getSeqnum().getTarget();
                        if (a != null) {
                            seenAddrs.add(a.getOffset());
                        }
                    }
                    Iterator<PcodeOp> uses = vn.getDescendants();
                    while (uses.hasNext()) {
                        PcodeOp use = uses.next();
                        Address a = use.getSeqnum().getTarget();
                        if (a != null) {
                            seenAddrs.add(a.getOffset());
                        }
                    }
                }
                int cap = 200;
                int count = 0;
                for (Long addr : seenAddrs) {
                    if (count >= cap) {
                        truncated = true;
                        break;
                    }
                    accessSites.add(addr);
                    count++;
                }
            } catch (Exception ex) {
                // Skip access sites on error
            }
        }
        v.add("access_sites", accessSites);
        v.addProperty("access_sites_truncated", truncated);

        return v;
    }
}
