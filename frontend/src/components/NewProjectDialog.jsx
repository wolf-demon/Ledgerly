import React, { useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "./ui/dialog";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Textarea } from "./ui/textarea";
import { Button } from "./ui/button";
import api from "../lib/api";
import { toast } from "sonner";

export default function NewProjectDialog({ open, onOpenChange, onCreated }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!name.trim()) {
      toast.error("Please enter a project name");
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.post("/projects", { name: name.trim(), description: description.trim() });
      toast.success(`Project "${res.data.name}" created`);
      setName("");
      setDescription("");
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
      <DialogContent className="bg-white border-[#EAE3D9]">
        <DialogHeader>
          <DialogTitle style={{ fontFamily: "Work Sans" }}>Create new project</DialogTitle>
          <DialogDescription className="text-[#656C5A]">
            Each project keeps its own transactions, categories and rules. Useful for separating personal and business finances.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="proj-name">Project name</Label>
            <Input
              id="proj-name"
              data-testid="new-project-name-input"
              placeholder="e.g. Personal 2025"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="proj-desc">Description (optional)</Label>
            <Textarea
              id="proj-desc"
              data-testid="new-project-desc-input"
              placeholder="Notes about this project"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
          </div>
        </div>
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
