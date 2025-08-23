import React from 'react';
import { headers } from 'next/headers';
import { redirect } from 'next/navigation';
import { auth } from '../../authentication/server_auth';
import UserSidebar from '../../components/UserSidebar';
import RequireAuth from '../../components/RequireAuth';

export default async function UserLayout({ children }: { children: React.ReactNode }) {
  const nh = headers();
  const session = await auth.api.getSession({ headers: nh });
  if (!session?.user?.id) {
    redirect('/login');
  }
  return (
    <RequireAuth>
      <div className="flex flex-1 min-h-0 h-full overflow-hidden p-4 gap-4">
        <div className="w-64 flex-shrink-0 flex flex-col bg-white border border-gray-300 rounded-lg overflow-hidden shadow-md min-h-0 h-full">
          <UserSidebar />
        </div>
        <div className="flex-1 flex flex-col min-h-0 h-full bg-white border border-gray-300 rounded-lg shadow-md overflow-hidden">
          <div className="flex-1 min-h-0 overflow-hidden">
            {children}
          </div>
        </div>
      </div>
    </RequireAuth>
  );
}


