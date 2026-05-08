import React, { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "./ui/dialog";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Textarea } from "./ui/textarea";
import { Button } from "./ui/button";
import api from "../lib/api";
import { toast } from "sonner";

/**
 * NOTE: inputs are intentionally UNCONTROLLED (refs + defaultValue).
 * Controlled inputs inside a Radix Dialog can stop accepting keystrokes
 * in some packaged-Electron / file:// contexts when the focus trap and
 * react-remove-scroll interact with our state updates. Uncontrolled
 * inputs sidestep the issue entirely — the value is read on submit.
 */
export default function NewProjectDialog({ open, onOpenChange, onCreated }) {
  const nameRef = useRef(null);
  const descRef = useRef(null);
  const [submitting, setSubmitting] = useState(false);

  // Clear inputs whenever the dialog is opened.
  useEffect(() => {
    if (open) {
      if (nameRef.current) nameRef.current.value = "";
      if (descRef.current) descRef.current.value = "";
      // Focus the name field shortly after Radix is finished mounting.
      const t = setTimeout(() => nameRef.current?.focus(), 80);
      return () => clearTimeout(t);
    }
  }, [open]);

  const submit = async () => {
    const name = (nameRef.current?.value || "").trim();
    const description = (descRef.current?.value || "").trim();
    if (!name) {
      toast.error("Please enter a project name");
      nameRef.current?.focus();
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.post("/projects", { name, description });
      toast.success(`Project "${res.data.name}" created`);
      onOpenChange(false);
      onCreated?.(res.data);
    } catch {
      toast.error("Failed to create project");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="bg-white border-[#EAE3D9]"
        onOpenAutoFocus={(e) => {
          // Let our own useEffect handle focusing the name field after mount.
          e.preventDefault();
        }}
      >
        <DialogHeader>
          <DialogTitle style={{ fontFamily: "Work Sans" }}>Create new project</DialogTitle>
          <DialogDescription className="text-[#656C5A]">
            Each project keeps its own transactions, categories and rules. Useful for separating personal and business finances.
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4 py-2"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="proj-name">Project name</Label>
            <Input
              ref={nameRef}
              id="proj-name"
              data-testid="new-project-name-input"
              placeholder="e.g. Personal 2025"
              defaultValue=""
              autoComplete="off"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="proj-desc">Description (optional)</Label>
            <Textarea
              ref={descRef}
              id="proj-desc"
              data-testid="new-project-desc-input"
              placeholder="Notes about this project"
              defaultValue=""
              rows={3}
            />
          </div>
          {/* Hidden submit so Enter in the name field triggers the form. */}
          <button type="submit" className="hidden" aria-hidden="true" />
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="cancel-new-project-btn">
            Cancel
          </Button>
          <Button
            onClick={submit}
            disabled={submitting}
            data-testid="submit-new-project-btn"
            className="bg-[#364C2E] hover:bg-[#22331D] text-white"
          >
            {submitting ? "Creating..." : "Create project"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
