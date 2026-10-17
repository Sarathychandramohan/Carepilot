import { useState, useEffect } from 'react';
import { useWorkflowStore } from '../services/mock/mockWorkflow';
import { useNavigate } from 'react-router-dom';
import { Search } from 'lucide-react';
import { patientApi } from '../services/api/patientApi';
import { Patient } from '../types';

export function PatientsPage() {
  const patients = useWorkflowStore(state => state.patients);
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [backendPatients, setBackendPatients] = useState<Patient[]>([]);

  useEffect(() => {
    setIsLoading(true);
    patientApi.getPatients(searchTerm)
      .then(items => {
        const mapped: Patient[] = items.map(p => ({
          id: p.id,
          firstName: p.firstName,
          lastName: p.lastName,
          dateOfBirth: p.dateOfBirth,
          gender: p.gender,
          age: p.age,
          conditions: Array(p.conditionsCount).fill(0).map((_, idx) => ({ id: `c-${idx}`, description: `Clinical Diagnosis #${idx + 1}`, startDate: '2020-01-01', active: true })),
          medications: Array(p.medicationsCount).fill(0).map((_, idx) => ({ id: `m-${idx}`, patientId: p.id, name: `Prescription #${idx + 1}`, dosage: 'Standard', frequency: 'Daily', startDate: '2020-01-01', active: true })),
          allergies: [],
          pendingConsultationCount: 0,
        }));
        setBackendPatients(mapped);
      })
      .catch(() => {
        // Fallback to store
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [searchTerm]);

  const allPatients = [
    ...patients,
    ...backendPatients.filter(bp => !patients.some(p => p.id === bp.id)),
  ];

  const filteredPatients = allPatients.filter(p => {
    const term = searchTerm.toLowerCase();
    const fullName = `${p.firstName} ${p.lastName}`.toLowerCase();
    return fullName.includes(term) || p.id.toLowerCase().includes(term);
  });

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-text-navy">Patients</h1>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-muted h-5 w-5" />
        <input
          type="text"
          placeholder="Search by patient name or ID..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="pl-10 w-full md:w-1/2 lg:w-1/3 rounded-md border-border-subtle shadow-sm focus:border-primary focus:ring-primary text-black py-2 px-3 border"
        />
      </div>

      <div className="bg-white shadow-sm rounded-lg border border-border-subtle overflow-hidden">
        {isLoading ? (
          <div className="divide-y divide-border-subtle">
            {[1, 2, 3].map(i => (
              <div key={i} className="px-6 py-4 animate-pulse flex justify-between items-center">
                <div className="w-1/4 h-5 bg-gray-200 rounded"></div>
                <div className="w-1/4 h-5 bg-gray-200 rounded"></div>
                <div className="w-1/4 h-5 bg-gray-200 rounded"></div>
                <div className="w-1/12 h-5 bg-gray-200 rounded"></div>
              </div>
            ))}
          </div>
        ) : filteredPatients.length === 0 ? (
          <div className="p-8 text-center text-text-muted">
            No patients match your search.
          </div>
        ) : (
          <table className="min-w-full divide-y divide-border-subtle">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">Age/Gender</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">Conditions</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">Pending Reviews</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">Last Consult</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-text-muted uppercase tracking-wider">Action</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-border-subtle">
              {filteredPatients.map(p => (
                <tr key={p.id} onClick={() => navigate(`/patients/${p.id}`)} className="hover:bg-gray-50 cursor-pointer">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="font-medium text-text-navy">{p.firstName} {p.lastName}</div>
                    <div className="text-xs text-text-muted">ID: {p.id}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm text-text-navy">{p.age}y / {p.gender}</div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-sm text-text-muted truncate max-w-[200px]">
                      {p.conditions.slice(0, 2).map(c => c.description).join(', ')}
                      {p.conditions.length > 2 && '...'}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    {p.pendingConsultationCount > 0 ? (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-urgent">
                        {p.pendingConsultationCount} Pending
                      </span>
                    ) : (
                      <span className="text-sm text-text-muted">None</span>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-text-muted">
                    {p.lastConsultation || 'N/A'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right">
                    <button className="text-primary hover:text-blue-700 font-medium text-sm">
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
