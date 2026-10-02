import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { FoundationPage } from "../pages/FoundationPage";
import { NotFoundPage } from "../pages/NotFoundPage";

const router = createBrowserRouter([
  { path: "/", element: <FoundationPage /> },
  { path: "*", element: <NotFoundPage /> },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
