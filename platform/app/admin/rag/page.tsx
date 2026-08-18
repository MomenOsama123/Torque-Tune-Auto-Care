"use client";

import { useState } from "react";
import {
  FileText,
  Upload,
  Trash2,
  Search,
} from "lucide-react";

const initialDocuments = [
  {
    id: "doc-001",
    name: "Company Knowledge Base.pdf",
    type: "PDF",
    size: "2.4 MB",
    uploaded: "Today",
    status: "Indexed",
  },
  {
    id: "doc-002",
    name: "Product Documentation.pdf",
    type: "PDF",
    size: "1.8 MB",
    uploaded: "Yesterday",
    status: "Indexed",
  },
  {
    id: "doc-003",
    name: "Support Guidelines.docx",
    type: "DOCX",
    size: "850 KB",
    uploaded: "2 days ago",
    status: "Processing",
  },
];

export default function RAGPage() {
  const [documents, setDocuments] = useState(initialDocuments);
  const [search, setSearch] = useState("");

  function deleteDocument(id: string) {
    setDocuments((current) =>
      current.filter((document) => document.id !== id)
    );
  }

  const filteredDocuments = documents.filter((document) =>
    document.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold">
            RAG Documents
          </h1>

          <p className="mt-2 text-muted-foreground">
            Upload and manage documents used by the RAG system.
          </p>
        </div>

        <button
          onClick={() =>
            alert("File upload will be connected to the RAG API.")
          }
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground hover:opacity-90"
        >
          <Upload className="h-4 w-4" />
          Upload Document
        </button>
      </div>

      {/* Search */}
      <div className="mb-5 flex max-w-md items-center gap-2 rounded-lg border px-3">
        <Search className="h-4 w-4 text-muted-foreground" />

        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search documents..."
          className="w-full bg-transparent py-2.5 text-sm outline-none"
        />
      </div>

      {/* Documents */}
      <div className="overflow-hidden rounded-xl border">
        <div className="grid grid-cols-12 border-b bg-muted/40 px-5 py-3 text-sm font-medium">
          <div className="col-span-4">Document</div>
          <div className="col-span-1">Type</div>
          <div className="col-span-2">Size</div>
          <div className="col-span-2">Uploaded</div>
          <div className="col-span-2">Status</div>
          <div className="col-span-1">Action</div>
        </div>

        {filteredDocuments.map((document) => (
          <div
            key={document.id}
            className="grid grid-cols-12 items-center border-b px-5 py-4 last:border-b-0"
          >
            {/* Document */}
            <div className="col-span-4 flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted">
                <FileText className="h-4 w-4" />
              </div>

              <div>
                <p className="text-sm font-medium">
                  {document.name}
                </p>

                <p className="text-xs text-muted-foreground">
                  {document.id}
                </p>
              </div>
            </div>

            {/* Type */}
            <div className="col-span-1 text-sm">
              {document.type}
            </div>

            {/* Size */}
            <div className="col-span-2 text-sm text-muted-foreground">
              {document.size}
            </div>

            {/* Uploaded */}
            <div className="col-span-2 text-sm text-muted-foreground">
              {document.uploaded}
            </div>

            {/* Status */}
            <div className="col-span-2">
              <span
                className={`rounded-full px-2.5 py-1 text-xs ${
                  document.status === "Indexed"
                    ? "bg-green-100 text-green-700"
                    : "bg-yellow-100 text-yellow-700"
                }`}
              >
                {document.status}
              </span>
            </div>

            {/* Delete */}
            <div className="col-span-1">
              <button
                onClick={() => deleteDocument(document.id)}
                className="rounded-md p-2 text-red-500 hover:bg-muted"
                title="Delete document"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))}

        {filteredDocuments.length === 0 && (
          <div className="p-10 text-center text-sm text-muted-foreground">
            No documents found.
          </div>
        )}
      </div>
    </div>
  );
}