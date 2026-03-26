import React from 'react';
import { Navigate } from 'react-router-dom';
import { User } from '../types';

interface AdminRouteProps {
    user: User | null;
    children: React.ReactNode;
}

const AdminRoute: React.FC<AdminRouteProps> = ({ user, children }) => {
    // Nếu chưa đăng nhập hoặc đăng nhập rồi nhưng không phải admin -> đá về '/'
    if (!user || user.is_admin !== true) {
        return <Navigate to="/" replace />;
    }

    return <>{children}</>;
};

export default AdminRoute;
