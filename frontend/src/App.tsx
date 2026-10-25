import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Layout } from "@/components/layout";
import { useSessao } from "@/lib/auth";
import PaginaDossie from "@/pages/dossie-detalhe";
import PaginaDossies from "@/pages/dossies";
import PaginaEmbarque from "@/pages/embarque-detalhe";
import PaginaEmbarques from "@/pages/embarques";
import PaginaFazenda from "@/pages/fazenda-detalhe";
import PaginaNovaFazenda from "@/pages/fazenda-nova";
import PaginaFazendas from "@/pages/fazendas";
import PaginaFornecedor from "@/pages/fornecedor-detalhe";
import PaginaFornecedores from "@/pages/fornecedores";
import PaginaLogin from "@/pages/login";

function Protegida() {
  const { autenticado } = useSessao();
  const local = useLocation();
  if (!autenticado) return <Navigate to="/login" replace state={{ de: local.pathname }} />;
  return <Layout />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<PaginaLogin />} />
      <Route element={<Protegida />}>
        <Route path="/" element={<Navigate to="/fazendas" replace />} />
        <Route path="/fazendas" element={<PaginaFazendas />} />
        <Route path="/fazendas/nova" element={<PaginaNovaFazenda />} />
        <Route path="/fazendas/:id" element={<PaginaFazenda />} />
        <Route path="/fornecedores" element={<PaginaFornecedores />} />
        <Route path="/fornecedores/:id" element={<PaginaFornecedor />} />
        <Route path="/embarques" element={<PaginaEmbarques />} />
        <Route path="/embarques/:id" element={<PaginaEmbarque />} />
        <Route path="/dossies" element={<PaginaDossies />} />
        <Route path="/dossies/:id" element={<PaginaDossie />} />
        <Route path="*" element={<Navigate to="/fazendas" replace />} />
      </Route>
    </Routes>
  );
}
