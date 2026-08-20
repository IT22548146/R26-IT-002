"use client";
import Swal from "@/lib/swal";

import { useState, useEffect } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Shirt, Plus, X, Search, Layers, Droplet, Type, PenTool, Edit2, Trash2 } from "lucide-react";

export default function AdminStylesDirectory() {
  const [styles, setStyles] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [isAdding, setIsAdding] = useState(false);
  const [editingStyleNumber, setEditingStyleNumber] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const [formData, setFormData] = useState({
    style_number: "",
    style_name: "",
    description: "",
    design_width: "",
    design_length: "",
    color_count: "",
    stitch_count: "",
    complexity: "Medium",
    garment_type: "",
  });

  const fetchStyles = async () => {
    try {
      const res = await api.get(`/styles?q=${searchQuery}`);
      setStyles(res.data);
    } catch (err) {
      console.error("Failed to fetch styles", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const delayDebounceFn = setTimeout(() => {
      fetchStyles();
    }, 300);
    return () => clearTimeout(delayDebounceFn);
  }, [searchQuery]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleEdit = (style: any) => {
    setFormData({
      style_number: style.style_number || "",
      style_name: style.style_name || "",
      description: style.description || "",
      design_width: style.design_width?.toString() || "",
      design_length: style.design_length?.toString() || "",
      color_count: style.color_count?.toString() || "",
      stitch_count: style.stitch_count?.toString() || "",
      complexity: style.complexity || "Medium",
      garment_type: style.garment_type || "",
    });
    setEditingStyleNumber(style.style_number);
    setIsAdding(true);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleDelete = async (style_number: string) => {
    const result = await Swal.fire({ title: "Confirm", text: `Are you sure you want to delete style ${style_number}?`, icon: 'warning', showCancelButton: true, confirmButtonColor: '#3085d6', cancelButtonColor: '#d33', confirmButtonText: 'Yes' });
    if (!result.isConfirmed) return;
    try {
      await api.delete(`/styles/${style_number}`);
      Swal.fire({ icon: 'success', title: "Style deleted successfully!" });
      fetchStyles();
    } catch (err: any) {
      Swal.fire({ icon: 'error', title: 'Error', text: err.response?.data?.error || "Failed to delete style." });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingStyleNumber) {
        await api.put(`/styles/${editingStyleNumber}`, formData);
        Swal.fire({ icon: 'success', title: "Style updated successfully!" });
      } else {
        await api.post("/styles", formData);
        Swal.fire({ icon: 'success', title: "Style added successfully!" });
      }
      setIsAdding(false);
      setEditingStyleNumber(null);
      setFormData({
        style_number: "",
        style_name: "",
        description: "",
        design_width: "",
        design_length: "",
        color_count: "",
        stitch_count: "",
        complexity: "Medium",
        garment_type: "",
      });
      fetchStyles();
    } catch (err: any) {
      Swal.fire({ icon: 'error', title: 'Error', text: err.response?.data?.error || "Failed to save style." });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <h2 className="text-xl font-bold text-slate-800 flex items-center">
          <Shirt className="w-6 h-6 mr-2 text-indigo-600" />
          Styles Directory
        </h2>
        
        <div className="flex items-center space-x-3 w-full sm:w-auto">
          <div className="relative w-full sm:w-64">
            <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
            <Input 
              placeholder="Search styles..." 
              className="pl-9"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          {!isAdding && (
            <Button onClick={() => setIsAdding(true)} className="bg-indigo-600 hover:bg-indigo-700 whitespace-nowrap">
              <Plus className="w-4 h-4 mr-2" />
              Add Style
            </Button>
          )}
        </div>
      </div>

      {isAdding && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 animate-in fade-in slide-in-from-top-4">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-lg font-bold text-slate-800">Add New Style</h3>
            <button onClick={() => setIsAdding(false)} className="text-slate-400 hover:text-slate-600">
              <X className="w-5 h-5" />
            </button>
          </div>
          
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700">Style Number *</label>
                <Input required name="style_number" value={formData.style_number} onChange={handleChange} placeholder="e.g. ART-001" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700">Style Name</label>
                <Input name="style_name" value={formData.style_name} onChange={handleChange} placeholder="e.g. Summer Floral" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700">Garment Type</label>
                <Input name="garment_type" value={formData.garment_type} onChange={handleChange} placeholder="e.g. T-Shirt" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700">Design Width (cm) *</label>
                <Input required type="number" step="0.1" name="design_width" value={formData.design_width} onChange={handleChange} placeholder="0.0" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700">Design Length (cm) *</label>
                <Input required type="number" step="0.1" name="design_length" value={formData.design_length} onChange={handleChange} placeholder="0.0" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700">Color Count *</label>
                <Input required type="number" name="color_count" value={formData.color_count} onChange={handleChange} placeholder="e.g. 5" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700">Stitch Count *</label>
                <Input required type="number" name="stitch_count" value={formData.stitch_count} onChange={handleChange} placeholder="e.g. 15000" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700">Complexity</label>
                <select 
                  name="complexity" 
                  value={formData.complexity} 
                  onChange={handleChange}
                  className="w-full px-3 py-2 bg-white border border-slate-300 rounded-md text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="Low">Low</option>
                  <option value="Medium">Medium</option>
                  <option value="High">High</option>
                  <option value="Hard">Hard</option>
                </select>
              </div>
            </div>
            
            <div className="space-y-2">
              <label className="text-sm font-semibold text-slate-700">Description</label>
              <textarea 
                name="description" 
                value={formData.description} 
                onChange={handleChange} 
                placeholder="Style description..."
                className="w-full px-3 py-2 bg-white border border-slate-300 rounded-md text-sm text-slate-900 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 h-24"
              />
            </div>

            <div className="flex justify-end pt-2">
              <Button type="button" variant="ghost" onClick={() => setIsAdding(false)} className="mr-3">Cancel</Button>
              <Button type="submit" className="bg-indigo-600 hover:bg-indigo-700">Save Style</Button>
            </div>
          </form>
        </div>
      )}

      {loading ? (
        <div className="text-slate-500">Loading styles...</div>
      ) : styles.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-12 text-center">
          <Shirt className="w-12 h-12 mx-auto text-slate-300 mb-4" />
          <h3 className="text-lg font-medium text-slate-900 mb-1">No Styles Found</h3>
          <p className="text-slate-500">Get started by adding a new style to the catalog.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {styles.map((style) => (
            <div key={style.style_number} className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden hover:shadow-md transition-shadow flex flex-col">
              <div className="p-5 border-b border-slate-100 bg-slate-50/50 flex justify-between items-start">
                <div>
                  <h3 className="text-lg font-bold text-slate-900 mb-1">{style.style_number}</h3>
                  <p className="text-sm text-slate-500 font-medium">{style.style_name || 'Unnamed Style'}</p>
                </div>
                <div className="flex flex-col items-end space-y-2">
                  <span className={`px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wider ${
                    style.complexity === 'Low' ? 'bg-emerald-100 text-emerald-800' :
                    style.complexity === 'Medium' ? 'bg-blue-100 text-blue-800' :
                    style.complexity === 'High' ? 'bg-amber-100 text-amber-800' :
                    'bg-red-100 text-red-800'
                  }`}>
                    {style.complexity || 'Medium'}
                  </span>
                  <div className="flex space-x-2">
                    <button onClick={() => handleEdit(style)} className="p-1 text-slate-400 hover:text-indigo-600 transition-colors" title="Edit">
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button onClick={() => handleDelete(style.style_number)} className="p-1 text-slate-400 hover:text-red-600 transition-colors" title="Delete">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
              
              <div className="p-5 space-y-4 flex-1">
                {style.description && (
                  <p className="text-sm text-slate-600 line-clamp-2 italic">"{style.description}"</p>
                )}
                
                <div className="grid grid-cols-2 gap-4 pt-2">
                  <div>
                    <div className="text-xs text-slate-400 font-semibold uppercase mb-1 flex items-center">
                      <Layers className="w-3 h-3 mr-1" /> Dimensions
                    </div>
                    <div className="text-sm font-medium text-slate-800">{style.design_width} x {style.design_length} cm</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400 font-semibold uppercase mb-1 flex items-center">
                      <Droplet className="w-3 h-3 mr-1" /> Colors
                    </div>
                    <div className="text-sm font-medium text-slate-800">{style.color_count} colors</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400 font-semibold uppercase mb-1 flex items-center">
                      <Type className="w-3 h-3 mr-1" /> Stitches
                    </div>
                    <div className="text-sm font-medium text-slate-800">{style.stitch_count?.toLocaleString()}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400 font-semibold uppercase mb-1 flex items-center">
                      <PenTool className="w-3 h-3 mr-1" /> Garment
                    </div>
                    <div className="text-sm font-medium text-slate-800">{style.garment_type || 'N/A'}</div>
                  </div>
                </div>
              </div>
              <div className="bg-slate-50 px-5 py-3 text-xs text-slate-400 border-t border-slate-100 flex justify-between">
                <span>Added by: {style.added_by_name || 'System'}</span>
                <span>{new Date(style.created_at).toLocaleDateString()}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
